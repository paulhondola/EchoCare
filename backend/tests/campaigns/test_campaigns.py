import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.campaigns.service import cancel_lapsed
from app.models import (
    Call,
    CallTrigger,
    Campaign,
    EnrollmentState,
    Grant,
    Incident,
    Role,
    SeniorStatus,
)
from app.status.engine import Severity
from app.voice.calls import CallState

DAS, MEDIC = "+40700000001", "+40700000002"
SENIOR, CAREGIVER, NO_GRANT = "+40700000101", "+40700000102", "+40700000009"

# Everyone but DAS (06 §5): each role, a number with no grant, signed out (None).
NOT_DAS = pytest.mark.parametrize(
    ("token", "status", "reason"),
    [
        (MEDIC, 403, "not_allowed"),
        (CAREGIVER, 403, "not_allowed"),
        (SENIOR, 403, "not_allowed"),
        (NO_GRANT, 403, "not_registered"),
        (None, 401, "not_signed_in"),
        ("invalid", 401, "not_signed_in"),
    ],
)


def signed_in(token):
    return {} if token is None else {"Authorization": f"Bearer {token}"}


async def start(client, kind="cold", level="yellow", token=DAS):
    return await client.post(
        "/api/campaigns",
        json={"kind": kind, "level": level},
        headers=signed_in(token),
    )


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


@pytest.fixture
async def everyone(db, add_user, add_active_senior):
    """A medic, an active senior with the senior grant, and that senior's caregiver."""
    await add_user(MEDIC, Role.medic)
    maria = await add_active_senior(SENIOR)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=maria.id))
    await db.commit()


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


@NOT_DAS
async def test_only_das_starts_or_lists(client, das, everyone, token, status, reason):
    refusal = (status, {"detail": {"reason": reason}})
    r = await start(client, token=token)
    assert (r.status_code, r.json()) == refusal
    r = await client.get("/api/campaigns", headers=signed_in(token))
    assert (r.status_code, r.json()) == refusal


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


async def end(client, campaign_id, token=DAS):
    return await client.post(
        f"/api/campaigns/{campaign_id}/end", headers=signed_in(token)
    )


async def test_ending_cancels_waiting_calls_and_keeps_codes(
    client, db, das, add_active_senior
):  # Q9
    maria = await add_active_senior("+40700000101")
    db.add(
        SeniorStatus(
            senior_id=maria.id,
            code=Severity.yellow,
            reason="x",
            since=datetime.now(UTC),
        )
    )
    await db.commit()
    c = (await start(client)).json()
    r = await end(client, c["id"])
    assert r.status_code == 200
    assert (
        r.json()["active"],
        r.json()["progress"]["canceled"],
        r.json()["progress"]["waiting"],
    ) == (False, 1, 0)
    assert (await db.scalar(select(Call.state))) is CallState.canceled
    assert (
        await db.get(SeniorStatus, maria.id, populate_existing=True)
    ).code is Severity.yellow
    assert (await end(client, c["id"])).json() == r.json()  # a repeat changes nothing
    assert (await start(client)).status_code == 201  # a new one may start (Q9)


async def test_a_landline_senior_waits_until_the_end(
    client, das, add_active_senior
):  # Review Focus 4
    await add_active_senior("+40256123456", landline=True)
    c = (await start(client)).json()
    assert c["progress"]["waiting"] == 1
    assert (await end(client, c["id"])).json()["progress"]["canceled"] == 1


async def test_ending_a_lapsed_campaign_keeps_its_end(client, db, das):
    c = (await start(client)).json()
    past = datetime.now(UTC) - timedelta(hours=1)
    await db.execute(update(Campaign).values(warning_until=past))
    await db.commit()
    assert (
        datetime.fromisoformat((await end(client, c["id"])).json()["warning_until"])
        == past
    )


async def test_a_lapsed_warning_frees_its_seniors(client, db, das, add_active_senior):
    await add_active_senior("+40700000101")
    await start(client)
    await db.execute(
        update(Campaign).values(warning_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    listed = (await client.get("/api/campaigns", headers=signed_in(DAS))).json()
    assert listed[0]["progress"]["canceled"] == 1
    assert (await start(client)).json()["progress"]["total"] == 1  # queued again


async def test_ending_an_unknown_campaign_is_404(client, das):
    assert (await end(client, uuid.uuid4())).json() == {
        "detail": {"reason": "not_found"}
    }


async def test_answering_a_running_campaign_still_cancels_a_lapsed_one(
    client, db, das, add_active_senior
):
    await add_active_senior("+40700000101")
    lapsing = (await start(client, "cold")).json()
    running = (await start(client, "heat")).json()
    await db.execute(
        update(Campaign)
        .where(Campaign.id == uuid.UUID(lapsing["id"]))
        .values(warning_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    again = await start(client, "heat")
    assert (again.status_code, again.json()["id"]) == (200, running["id"])
    assert (await db.scalar(select(Call.state))) is CallState.canceled


@NOT_DAS
async def test_only_das_ends(client, das, everyone, token, status, reason):
    c = (await start(client)).json()
    r = await end(client, c["id"], token)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    listed = (await client.get("/api/campaigns", headers=signed_in(DAS))).json()
    assert [x["active"] for x in listed] == [True]  # the refusal changed nothing


async def test_ending_cancels_a_redial_and_leaves_another_campaign_alone(
    client, db, das, add_active_senior
):  # Q9
    maria = await add_active_senior("+40700000101")
    a = (await start(client, "cold", "yellow")).json()
    ion = await add_active_senior("+40700000102")
    b = (await start(client, "cold", "red")).json()  # Maria's call is A's: only Ion
    assert b["progress"]["waiting"] == 1

    first = await db.scalar(select(Call).where(Call.senior_id == maria.id))
    first.state, first.ended_at = CallState.unanswered, datetime.now(UTC)
    await db.commit()
    db.add(  # A's redial, queued after the first attempt ended
        Call(
            senior_id=maria.id,
            trigger=CallTrigger.campaign,
            campaign_id=first.campaign_id,
            previous_call_id=first.id,
            attempt=2,
            starting_severity=Severity.green,
            state=CallState.queued,
            due_at=datetime.now(UTC),
        )
    )
    await db.commit()

    r = await end(client, a["id"])
    assert r.json()["progress"]["canceled"] == 1
    states = {
        (c.senior_id, c.attempt): c.state
        for c in (await db.scalars(select(Call))).all()
    }
    assert states == {
        (maria.id, 1): CallState.unanswered,  # a finished attempt is history
        (maria.id, 2): CallState.canceled,
        (ion.id, 1): CallState.queued,  # B's call is untouched
    }
    listed = {
        c["id"]: c
        for c in (await client.get("/api/campaigns", headers=signed_in(DAS))).json()
    }
    assert (listed[a["id"]]["active"], listed[b["id"]]["active"]) == (False, True)


async def start_with_a_dialed_call(client, db, add_active_senior):
    """A campaign with two queued calls, the older one dialed: Twilio has been asked
    (`dialed_at`), and its status callback, not the campaign, settles it."""
    await add_active_senior("+40700000101")
    await add_active_senior("+40700000102")
    c = (await start(client)).json()
    dialed, waiting = (await db.scalars(select(Call).order_by(Call.created_at))).all()
    dialed.dialed_at = datetime.now(UTC)
    await db.commit()
    return c, dialed.id, waiting.id


async def test_a_lapsed_campaign_leaves_a_dialed_call(
    client, db, das, add_active_senior
):
    _, dialed, waiting = await start_with_a_dialed_call(client, db, add_active_senior)
    await db.execute(
        update(Campaign).values(warning_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    await cancel_lapsed(db)
    await db.commit()
    states = {x.id: x.state for x in await db.scalars(select(Call))}
    assert states == {dialed: CallState.queued, waiting: CallState.canceled}


async def test_ending_a_campaign_leaves_a_dialed_call(
    client, db, das, add_active_senior
):
    c, dialed, waiting = await start_with_a_dialed_call(client, db, add_active_senior)
    r = await end(client, c["id"])
    assert r.status_code == 200
    states = {x.id: x.state for x in await db.scalars(select(Call))}
    assert states == {dialed: CallState.queued, waiting: CallState.canceled}
