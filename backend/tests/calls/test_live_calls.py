"""GET /calls/live: the calls the dashboard shows as they happen (design 2026-11-14 §4)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Call, CallTrigger, CallTurn, Role
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.models import Speaker, TurnKind

DAS = "+40700000001"
MEDIC = "+40700000002"


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def maria(add_user, add_active_senior):
    await add_user(DAS, Role.das)
    return await add_active_senior("+40700000101")


async def add_call(db, senior, state, *, minutes_ago=0, **fields) -> Call:
    call = Call(
        senior_id=senior.id,
        trigger=fields.pop("trigger", CallTrigger.campaign),
        starting_severity=Severity.green,
        state=state,
        due_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        **fields,
    )
    db.add(call)
    await db.commit()
    return call


async def add_turn(db, call, seconds_ago: int, position: int = 0) -> None:
    db.add(
        CallTurn(
            call_id=call.id,
            position=position,
            speaker=Speaker.das,
            kind=TurnKind.speech,
            content="Bună ziua, sunt de la DAS.",
            at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
        )
    )
    await db.commit()


async def live_ids(client) -> list[str]:
    r = await client.get("/api/calls/live", headers=signed_in(DAS))
    assert r.status_code == 200
    return [row["id"] for row in r.json()]


async def test_ringing_and_in_progress_calls_are_live(
    client, db, maria, add_active_senior
):
    # One queued, ringing or talking call per senior (uq_calls_live_senior)
    ion = await add_active_senior("+40700000102")
    ana = await add_active_senior("+40700000103")
    ringing = await add_call(db, ion, CallState.ringing, minutes_ago=2)
    talking = await add_call(db, maria, CallState.in_progress, minutes_ago=1)
    await add_call(db, ana, CallState.queued)
    await add_call(db, maria, CallState.completed, minutes_ago=3)

    r = await client.get("/api/calls/live", headers=signed_in(DAS))

    assert r.status_code == 200
    rows = r.json()
    assert [row["id"] for row in rows] == [str(talking.id), str(ringing.id)]
    assert rows[0]["senior_name"] == maria.full_name
    assert rows[0]["senior_id"] == str(maria.id)
    assert rows[0]["starting_severity"] == "green"
    assert rows[0]["trigger"] == "campaign"


async def test_a_hand_over_stays_live_while_das_talks(client, db, maria):
    ended = datetime.now(UTC)
    # Briefing, ring and DAS's first sentence can leave a minute without a turn
    talking = await add_call(db, maria, CallState.handed_over, ended_at=ended)
    await add_turn(db, talking, seconds_ago=60)
    quiet = await add_call(db, maria, CallState.handed_over, ended_at=ended)
    await add_turn(db, quiet, seconds_ago=120)
    await add_call(db, maria, CallState.handed_over, ended_at=ended)

    assert await live_ids(client) == [str(talking.id)]


async def test_test_calls_are_not_live(client, db, maria):
    await add_call(db, maria, CallState.in_progress, trigger=CallTrigger.test)

    assert await live_ids(client) == []


async def test_only_das_sees_live_calls(client, add_user, maria):
    await add_user(MEDIC, Role.medic)

    r = await client.get("/api/calls/live", headers=signed_in(MEDIC))

    assert r.status_code == 403
