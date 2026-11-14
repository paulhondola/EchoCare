"""POST /me/check-ins, the watch silence step, and the watch's readings (UC-13, #47,
ADR-006)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import (
    EnrollmentState,
    Grant,
    Role,
    WatchCondition,
    WatchReading,
    WatchState,
)
from app.seniors.service import prune_watch_readings, silence_watches, watch_silence
from tests.seniors.test_seniors import NOT_ALLOWED, refusal, signed_in

SENIOR = "+40700000101"
MEDIC = "+40700000102"
CAREGIVER = "+40700000103"
DAS = "+40700000104"


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


def check_in(client, measured_at=None, token=SENIOR, **fields):
    measured_at = measured_at or datetime.now(UTC)
    return client.post(
        "/api/me/check-ins",
        json={"measured_at": measured_at.isoformat(), **fields},
        headers=signed_in(token),
    )


async def stored(db, senior) -> WatchState:
    """The test's one watch state; `senior` only says a senior exists."""
    db.expire_all()
    return await db.scalar(select(WatchState))


async def test_a_first_check_in_creates_the_watch_state(client, db, senior):
    r = await check_in(client, battery=80, worn=True, last_pulse=72)
    assert r.status_code == 204
    watch = await stored(db, senior)
    assert (watch.state, watch.battery, watch.worn, watch.last_pulse) == (
        WatchCondition.ok,
        80,
        True,
        72,
    )


async def test_not_worn(client, db, senior):
    await check_in(client, worn=False)
    assert (await stored(db, senior)).state is WatchCondition.not_worn


async def test_an_older_check_in_changes_nothing(client, db, senior):
    first = datetime.now(UTC) - timedelta(minutes=1)
    await check_in(client, first, battery=80)
    await check_in(client, first - timedelta(minutes=5), battery=10, worn=False)
    watch = await stored(db, senior)
    assert (watch.last_check_in_at, watch.battery, watch.state) == (
        first,
        80,
        WatchCondition.ok,
    )


async def test_a_future_time_is_stored_as_arrival(client, db, senior):
    before = datetime.now(UTC)
    await check_in(client, before + timedelta(hours=1))
    stamp = (await stored(db, senior)).last_check_in_at
    assert before <= stamp <= datetime.now(UTC)


async def test_a_naive_time_is_422(client, senior):
    r = await client.post(
        "/api/me/check-ins",
        json={"measured_at": "2026-10-24T10:00:00"},
        headers=signed_in(SENIOR),
    )
    assert r.status_code == 422


async def test_only_a_senior_checks_in(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    assert refusal(await check_in(client, token=MEDIC)) == NOT_ALLOWED


async def test_a_silent_watch_goes_offline_and_comes_back(
    db, client, senior, monkeypatch
):
    monkeypatch.setattr(
        "app.seniors.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    now = datetime.now(UTC)
    await check_in(client, now - timedelta(minutes=50))
    assert await silence_watches(db, now) == 1
    assert (await stored(db, senior)).state is WatchCondition.offline
    await check_in(client, now)
    assert (await stored(db, senior)).state is WatchCondition.ok


async def test_a_watch_inside_the_limit_stays(db, client, senior, monkeypatch):
    monkeypatch.setattr(
        "app.seniors.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    now = datetime.now(UTC)
    await check_in(client, now - timedelta(minutes=30))
    assert await silence_watches(db, now) == 0
    assert (await stored(db, senior)).state is WatchCondition.ok


def test_silence_is_90_seconds_in_demo_mode(monkeypatch):
    for demo, limit in ((True, timedelta(seconds=90)), (False, timedelta(minutes=45))):
        monkeypatch.setattr(
            "app.seniors.service.get_settings",
            lambda demo=demo: SimpleNamespace(demo_mode=demo),
        )
        assert watch_silence() == limit


@pytest.fixture
async def watched(db, add_user, add_senior):
    """A senior whose watch is not worn, with everyone who can open her page."""
    medic = await add_user(MEDIC, Role.medic)
    maria = await add_senior(
        SENIOR, medic=medic, enrollment_state=EnrollmentState.accepted
    )
    herself = await add_user(SENIOR)
    caregiver = await add_user(CAREGIVER)
    other = await add_senior("+40700000105", medic=medic)
    das = await add_user(DAS, Role.das)
    db.add_all(
        [
            Grant(user_id=herself.id, role=Role.senior, senior_id=maria.id),
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=maria.id),
            # Reaches Maria as DAS only: caring for someone else shows no watch of hers
            Grant(user_id=das.id, role=Role.caregiver, senior_id=other.id),
            WatchState(
                senior_id=maria.id,
                state=WatchCondition.not_worn,
                last_check_in_at=datetime.now(UTC),
            ),
        ]
    )
    await db.commit()
    return SimpleNamespace(maria=maria, other=other)


@pytest.mark.parametrize(
    ("token", "state"),
    [
        (CAREGIVER, "not_worn"),
        (MEDIC, "not_worn"),
        (DAS, "not_worn"),
        (SENIOR, "not_worn"),
    ],
)
async def test_who_looks_after_her_sees_the_watch(client, watched, token, state):
    """UC-12: the caregiver's, the medic's and DAS's page show it (ADR-006); UC-03:
    so does her own."""
    r = await client.get(f"/api/seniors/{watched.maria.id}", headers=signed_in(token))
    assert r.status_code == 200
    assert r.json()["watch_state"] == state


async def test_no_watch_yet_is_no_state(client, watched):
    r = await client.get(f"/api/seniors/{watched.other.id}", headers=signed_in(MEDIC))
    assert r.json()["watch_state"] is None


async def rows(client, token, role=None):
    r = await client.get(
        "/api/seniors",
        params={"role": role} if role else None,
        headers=signed_in(token),
    )
    assert r.status_code == 200
    return {row["id"]: row for row in r.json()}


@pytest.mark.parametrize(
    ("token", "role"), [(MEDIC, "medic"), (CAREGIVER, "caregiver")]
)
async def test_the_rows_carry_the_watch_state_for_her_medic_and_caregiver(
    client, watched, token, role
):
    """UC-12: the same rule as her page, on the list."""
    await check_in(client, worn=False)
    found = await rows(client, token, role)
    assert found[str(watched.maria.id)]["watch_state"] == "not_worn"


async def test_das_rows_carry_the_watch_state(client, watched):
    """ADR-006: DAS sees the watch like her medic does."""
    found = await rows(client, DAS, "das")
    assert found[str(watched.maria.id)]["watch_state"] == "not_worn"


async def test_no_check_in_yet_is_null_on_the_row(client, watched):
    found = await rows(client, MEDIC, "medic")
    assert found[str(watched.other.id)]["watch_state"] is None


# The readings and GET /seniors/{id}/watch[/readings] (04 §1, ADR-006)


async def readings(db) -> int:
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(WatchReading))


async def test_a_check_in_stores_the_new_fields_and_a_reading(client, db, watched):
    r = await check_in(
        client,
        last_pulse=72,
        resting_pulse=64,
        steps_today=1200,
        minutes_without_steps=7,
    )
    assert r.status_code == 204
    watch = await stored(db, watched)
    assert (watch.resting_pulse, watch.steps_today, watch.minutes_without_steps) == (
        64,
        1200,
        7,
    )
    assert await readings(db) == 1


async def test_a_resent_check_in_is_one_reading(client, db, watched):
    at = datetime.now(UTC) - timedelta(minutes=1)
    await check_in(client, at, last_pulse=70)
    await check_in(client, at, last_pulse=70)
    assert await readings(db) == 1


async def test_an_old_phone_still_checks_in(client, db, watched):
    """No new field: 204, as before ADR-006."""
    assert (await check_in(client, battery=50)).status_code == 204
    assert await readings(db) == 1


async def test_the_watch_view(client, watched):
    await check_in(client, battery=81, worn=True, last_pulse=75, steps_today=300)
    r = await client.get(
        f"/api/seniors/{watched.maria.id}/watch", headers=signed_in(DAS)
    )
    assert r.status_code == 200
    body = r.json()
    assert (
        body["state"],
        body["battery"],
        body["last_pulse"],
        body["steps_today"],
    ) == (
        "ok",
        81,
        75,
        300,
    )
    assert body["resting_pulse"] is None


async def test_no_check_in_yet_is_204(client, watched):
    r = await client.get(
        f"/api/seniors/{watched.other.id}/watch", headers=signed_in(MEDIC)
    )
    assert r.status_code == 204


async def test_a_stranger_does_not_reach_the_watch(client, watched):
    """The caregiver reaches Maria only; the other senior is not hers."""
    for path in ("watch", "watch/readings"):
        r = await client.get(
            f"/api/seniors/{watched.other.id}/{path}", headers=signed_in(CAREGIVER)
        )
        assert r.status_code == 404


async def test_readings_come_in_five_minute_buckets_of_the_last_day(client, watched):
    now = datetime.now(UTC)
    start = now.replace(second=0, microsecond=0) - timedelta(
        minutes=now.minute % 5 + 10
    )
    # Two check-ins in one bucket, one in the next, one older than a day
    await check_in(client, start, last_pulse=70, battery=90, worn=True)
    await check_in(client, start + timedelta(minutes=1), last_pulse=81, battery=89)
    await check_in(client, start + timedelta(minutes=5), last_pulse=60, worn=False)
    await check_in(client, now - timedelta(hours=25), last_pulse=200)
    r = await client.get(
        f"/api/seniors/{watched.maria.id}/watch/readings", headers=signed_in(SENIOR)
    )
    assert r.status_code == 200
    first, second = r.json()
    assert datetime.fromisoformat(first["at"]) == start
    assert (first["pulse"], first["battery"], first["worn"]) == (76, 89, True)
    assert (second["pulse"], second["worn"]) == (60, False)


async def test_prune_deletes_only_readings_older_than_a_day(client, db, watched):
    now = datetime.now(UTC)
    await check_in(client, now - timedelta(hours=25))
    await check_in(client, now - timedelta(hours=1))
    assert await prune_watch_readings(db, now) == 1
    assert await readings(db) == 1
