"""POST /me/health-readings: blood oxygen and ECG from Apple Health (design 2026-11-14)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import EcgClassification, HealthReading, HealthReadingKind, Role
from app.seniors.service import prune_health_readings
from tests.seniors.test_seniors import NOT_ALLOWED, refusal, signed_in

SENIOR = "+40700000101"
SENIOR_2 = "+40700000106"
MEDIC = "+40700000102"
ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


def post(client, measured_at=None, token=SENIOR, **fields):
    measured_at = measured_at or datetime.now(UTC)
    return client.post(
        "/api/me/health-readings",
        json={"measured_at": measured_at.isoformat(), **fields},
        headers=signed_in(token),
    )


async def count(db) -> int:
    return await db.scalar(select(func.count()).select_from(HealthReading))


async def test_an_spo2_reading_is_stored(client, db, senior):
    r = await post(client, id=str(ID), kind="spo2", spo2=97)
    assert r.status_code == 204
    row = await db.scalar(select(HealthReading))
    assert (row.id, row.kind, row.spo2, row.senior_id) == (
        ID,
        HealthReadingKind.spo2,
        97,
        senior.id,
    )


async def test_an_ecg_is_stored_with_its_trace(client, db, senior):
    r = await post(
        client,
        id=str(ID),
        kind="ecg",
        ecg_classification="sinus_rhythm",
        ecg_heart_rate=72,
        ecg_trace=[1, -2, 3],
        ecg_trace_hz=128,
    )
    assert r.status_code == 204
    row = await db.scalar(select(HealthReading))
    assert (row.ecg_classification, row.ecg_trace, row.ecg_trace_hz) == (
        EcgClassification.sinus_rhythm,
        [1, -2, 3],
        128,
    )


async def test_a_duplicate_is_204_and_stored_once(client, db, senior):
    first = await post(client, id=str(ID), kind="spo2", spo2=97)
    second = await post(client, id=str(ID), kind="spo2", spo2=90)
    assert (first.status_code, second.status_code) == (204, 204)
    assert await count(db) == 1
    assert (await db.scalar(select(HealthReading.spo2))) == 97


async def test_the_same_id_for_two_seniors_is_stored_twice(
    client, db, senior, add_active_senior
):
    await add_active_senior(SENIOR_2)
    await post(client, id=str(ID), kind="spo2", spo2=97)
    await post(client, id=str(ID), kind="spo2", spo2=97, token=SENIOR_2)
    assert await count(db) == 2


async def test_a_future_time_is_stored_as_arrival(client, db, senior):
    now = datetime.now(UTC)
    await post(client, now + timedelta(hours=1), id=str(ID), kind="spo2", spo2=97)
    stored = await db.scalar(select(HealthReading.measured_at))
    assert abs(stored - now) < timedelta(seconds=5)


async def test_older_than_a_day_is_not_stored(client, db, senior):
    r = await post(
        client,
        datetime.now(UTC) - timedelta(hours=25),
        id=str(ID),
        kind="spo2",
        spo2=97,
    )
    assert r.status_code == 204
    assert await count(db) == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "spo2"},
        {"kind": "spo2", "spo2": 97, "ecg_heart_rate": 70},
        {"kind": "spo2", "spo2": 49},
        {"kind": "ecg"},
        {"kind": "ecg", "ecg_classification": "sinus_rhythm", "spo2": 97},
        {"kind": "ecg", "ecg_classification": "sinus_rhythm", "ecg_trace": [1]},
        {
            "kind": "ecg",
            "ecg_classification": "sinus_rhythm",
            "ecg_trace": [0] * 1_281,
            "ecg_trace_hz": 128,
        },
        {
            "kind": "ecg",
            "ecg_classification": "sinus_rhythm",
            "ecg_trace": [10_001],
            "ecg_trace_hz": 128,
        },
        {"kind": "ecg", "ecg_classification": "bogus"},
    ],
)
async def test_a_bad_body_is_422(client, db, senior, fields):
    r = await post(client, id=str(ID), **fields)
    assert r.status_code == 422
    assert await count(db) == 0


async def test_a_naive_time_is_422(client, senior):
    r = await client.post(
        "/api/me/health-readings",
        json={
            "id": str(ID),
            "kind": "spo2",
            "spo2": 97,
            "measured_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        },
        headers=signed_in(SENIOR),
    )
    assert r.status_code == 422


async def test_only_a_senior_may_post(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    r = await post(client, id=str(ID), kind="spo2", spo2=97, token=MEDIC)
    assert refusal(r) == NOT_ALLOWED


# GET /seniors/{id}/watch/health

DAS = "+40700000104"


def health(client, senior, token=DAS):
    return client.get(
        f"/api/seniors/{senior.id}/watch/health", headers=signed_in(token)
    )


async def test_health_shows_the_latest_spo2_the_day_and_the_latest_ecg(
    client, add_user, senior
):
    await add_user(DAS, Role.das)
    now = datetime.now(UTC)
    ecg = {"kind": "ecg", "ecg_classification": "sinus_rhythm", "ecg_trace_hz": 128}
    await post(
        client, now - timedelta(hours=2), id=str(uuid.uuid4()), kind="spo2", spo2=95
    )
    await post(
        client, now - timedelta(hours=1), id=str(uuid.uuid4()), kind="spo2", spo2=97
    )
    await post(
        client, now - timedelta(hours=3), id=str(uuid.uuid4()), ecg_trace=[1], **ecg
    )
    await post(
        client,
        now - timedelta(minutes=30),
        id=str(uuid.uuid4()),
        ecg_heart_rate=72,
        ecg_trace=[4, 5],
        **{**ecg, "ecg_classification": "atrial_fibrillation"},
    )
    r = await health(client, senior)
    assert r.status_code == 200
    body = r.json()
    assert body["spo2"]["value"] == 97
    assert [p["value"] for p in body["spo2_readings"]] == [95, 97]
    assert body["ecg"]["classification"] == "atrial_fibrillation"
    assert (body["ecg"]["trace"], body["ecg"]["heart_rate"]) == ([4, 5], 72)


async def test_health_is_204_with_no_readings(client, add_user, senior):
    await add_user(DAS, Role.das)
    assert (await health(client, senior)).status_code == 204


async def test_health_is_out_of_reach_for_a_stranger(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    r = await health(client, senior, MEDIC)
    watch = await client.get(
        f"/api/seniors/{senior.id}/watch", headers=signed_in(MEDIC)
    )
    assert refusal(r) == refusal(watch) == (404, {"detail": {"reason": "not_found"}})


async def test_the_senior_sees_their_own_health(client, senior):
    await post(client, id=str(ID), kind="spo2", spo2=96)
    r = await health(client, senior, SENIOR)
    assert r.json()["spo2"]["value"] == 96
    assert r.json()["ecg"] is None


async def test_readings_past_a_day_are_not_served(client, db, add_user, senior):
    await add_user(DAS, Role.das)
    db.add(
        HealthReading(
            senior_id=senior.id,
            id=ID,
            kind=HealthReadingKind.spo2,
            measured_at=datetime.now(UTC) - timedelta(hours=25),
            spo2=90,
        )
    )
    await db.commit()
    assert (await health(client, senior)).status_code == 204


async def test_prune_deletes_health_readings_older_than_a_day(db, senior):
    now = datetime.now(UTC)
    db.add_all(
        HealthReading(
            senior_id=senior.id,
            id=uuid.uuid4(),
            kind=HealthReadingKind.spo2,
            measured_at=now - age,
            spo2=97,
        )
        for age in (timedelta(hours=25), timedelta(hours=1))
    )
    await db.commit()
    assert await prune_health_readings(db, now) == 1
    assert await count(db) == 1
