import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Call, CallTrigger, Campaign, EnrollmentState, Incident, Role
from app.status.engine import Severity
from app.voice.calls import CallState

DAS, MEDIC = "+40700000001", "+40700000002"


def signed_in(token):
    return {"Authorization": f"Bearer {token}"}


async def start(client, kind="cold", level="yellow", token=DAS):
    return await client.post(
        "/api/campaigns",
        json={"kind": kind, "level": level},
        headers=signed_in(token),
    )


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


async def test_a_campaign_queues_one_call_per_active_senior(
    client, db, das, add_active_senior, add_senior
):
    maria = await add_active_senior("+40700000101")
    await add_senior("+40700000102", enrollment_state=EnrollmentState.accepted)
    busy = await add_active_senior("+40700000103")
    db.add(Incident(senior_id=busy.id, reason="Căzătură"))  # unresolved
    await db.commit()
    r = await start(client)
    assert r.status_code == 201
    body = r.json()
    assert (body["kind"], body["level"], body["started_by_name"], body["active"]) == (
        "cold",
        "yellow",
        "DAS Test",
        True,
    )
    assert body["progress"] == {
        "total": 1,
        "waiting": 1,
        "green": 0,
        "yellow": 0,
        "red": 0,
        "canceled": 0,
    }
    started, until = (
        datetime.fromisoformat(body[k]) for k in ("started_at", "warning_until")
    )
    assert until - started == timedelta(hours=24)  # Q4
    calls = (await db.scalars(select(Call))).all()
    assert [
        (c.senior_id, c.trigger, c.attempt, c.starting_severity, c.state) for c in calls
    ] == [(maria.id, CallTrigger.campaign, 1, Severity.green, CallState.queued)]


async def test_a_senior_with_a_live_call_is_skipped(client, db, das, add_active_senior):
    maria = await add_active_senior("+40700000101")
    db.add(
        Call(
            senior_id=maria.id,
            trigger=CallTrigger.test,
            starting_severity=Severity.green,
            due_at=datetime.now(UTC),
        )
    )
    await db.commit()
    assert (await start(client)).json()["progress"]["total"] == 0


async def test_the_same_kind_and_level_answers_the_running_campaign(
    client, das, add_active_senior
):  # Q3
    await add_active_senior("+40700000101")
    first = (await start(client)).json()
    again = await start(client)
    assert (again.status_code, again.json()["id"]) == (200, first["id"])
    other = await start(client, level="red")
    assert other.status_code == 201 and other.json()["id"] != first["id"]
    assert (
        other.json()["progress"]["total"] == 0
    )  # Maria's call is the first campaign's


async def test_two_presses_at_once_make_one_campaign(client, db, das):  # Review Focus 1
    a, b = await asyncio.gather(start(client), start(client))
    assert sorted([a.status_code, b.status_code]) == [200, 201]
    assert a.json()["id"] == b.json()["id"]
    assert await db.scalar(select(func.count()).select_from(Campaign)) == 1


async def test_no_active_seniors_is_still_a_campaign(client, das):  # Review Focus 5
    r = await start(client)
    assert (r.status_code, r.json()["progress"]["total"]) == (201, 0)


async def test_the_list_is_newest_first(client, das):
    await start(client, "cold")
    await start(client, "heat")
    r = await client.get("/api/campaigns", headers=signed_in(DAS))
    assert [c["kind"] for c in r.json()] == ["heat", "cold"]


@pytest.mark.parametrize(
    ("token", "status"), [(MEDIC, 403), ("+40700000009", 403), ("invalid", 401)]
)
async def test_only_das_starts_or_lists(client, das, add_user, token, status):
    await add_user(MEDIC, Role.medic)
    assert (await start(client, token=token)).status_code == status
    assert (
        await client.get("/api/campaigns", headers=signed_in(token))
    ).status_code == status


async def test_a_bad_body_is_422(client, das):
    assert (await start(client, kind="rain")).status_code == 422


async def test_progress_counts_each_senior_by_their_latest_attempt(
    client, db, das, add_active_senior
):
    redialed, red, canceled, _untouched = [
        await add_active_senior(f"+4070000010{i}") for i in range(1, 5)
    ]
    await start(client)
    calls = {c.senior_id: c for c in (await db.scalars(select(Call))).all()}
    now = datetime.now(UTC)
    first = calls[redialed.id]
    first.state, first.final_severity, first.ended_at = (
        CallState.unanswered,
        Severity.yellow,
        now,
    )
    calls[red.id].state, calls[red.id].final_severity = (
        CallState.completed,
        Severity.red,
    )
    calls[canceled.id].state = CallState.canceled
    await db.commit()
    db.add(  # the redial: the first attempt's yellow no longer counts
        Call(
            senior_id=redialed.id,
            trigger=CallTrigger.campaign,
            campaign_id=first.campaign_id,
            previous_call_id=first.id,
            attempt=2,
            starting_severity=Severity.green,
            due_at=now,
        )
    )
    await db.commit()
    r = await client.get("/api/campaigns", headers=signed_in(DAS))
    assert r.json()[0]["progress"] == {
        "total": 4,
        "waiting": 2,
        "green": 0,
        "yellow": 0,
        "red": 1,
        "canceled": 1,
    }
