from datetime import UTC, datetime, timedelta
from itertools import count
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.models import Call, CallTrigger
from app.scheduler.sweep import sweep
from app.status.engine import Severity
from app.voice.calls import CallState

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def twilio(monkeypatch):
    """Twilio's reads and hang-ups, patched where the sweep uses them."""
    fetch = AsyncMock(return_value=("completed", None))
    hang = AsyncMock()
    monkeypatch.setattr("app.scheduler.sweep.fetch_call", fetch)
    monkeypatch.setattr("app.scheduler.sweep.hang_up", hang)
    return fetch, hang


@pytest.fixture
def add_call(db, add_active_senior):
    """add_call(): a campaign call dialed `ago` ago, for a new active senior."""
    numbers = count(110)

    async def add(ago=timedelta(minutes=5), **columns) -> Call:
        senior = await add_active_senior(f"+40700000{next(numbers)}")
        call = Call(
            **{
                "senior_id": senior.id,
                "trigger": CallTrigger.campaign,
                "starting_severity": Severity.green,
                "due_at": NOW - timedelta(hours=1),
                "dialed_at": NOW - ago,
                "state": CallState.in_progress,
                **columns,
            }
        )
        db.add(call)
        await db.commit()
        return call

    return add


async def row(db, call: Call) -> Call:
    await db.refresh(call)
    return call


async def test_a_call_stuck_in_progress_is_settled_from_twilio(db, twilio, add_call):
    fetch, hang = twilio
    call = await add_call(twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    fetch.assert_awaited_once_with("CA1")
    hang.assert_not_awaited()
    assert (await row(db, call)).state is CallState.dropped


async def test_a_call_twilio_still_has_live_is_hung_up_first(db, twilio, add_call):
    fetch, hang = twilio
    fetch.side_effect = [("in-progress", None), ("completed", None)]
    call = await add_call(twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    hang.assert_awaited_once_with("CA1", "in-progress")
    assert (await row(db, call)).state is CallState.dropped


async def test_an_initiated_call_is_canceled_like_a_queued_one(db, twilio, add_call):
    fetch, hang = twilio
    fetch.side_effect = [("initiated", None), ("canceled", None)]
    call = await add_call(state=CallState.queued, twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    hang.assert_awaited_once_with("CA1", "queued")
    assert (await row(db, call)).state is CallState.unanswered


async def test_a_call_stuck_ringing_without_a_sid_fails(db, twilio, add_call):
    fetch, _ = twilio
    call = await add_call(state=CallState.ringing)

    assert await sweep(NOW) == 1

    fetch.assert_not_awaited()
    assert (await row(db, call)).state is CallState.failed
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert redial.attempt == 2 and redial.state is CallState.queued


async def test_a_call_inside_the_limit_is_left_alone(db, twilio, add_call):
    fetch, _ = twilio
    call = await add_call(ago=timedelta(minutes=2), twilio_call_id="CA1")

    assert await sweep(NOW) == 0

    fetch.assert_not_awaited()
    assert (await row(db, call)).state is CallState.in_progress


async def test_a_twilio_error_on_one_call_does_not_stop_the_sweep(db, twilio, add_call):
    fetch, _ = twilio
    fetch.side_effect = [httpx.ReadTimeout("x"), ("completed", None)]
    first = await add_call(twilio_call_id="CA1")
    second = await add_call(twilio_call_id="CA2")
    first, second = sorted((first, second), key=lambda c: c.id)

    assert await sweep(NOW) == 1

    assert (await row(db, first)).state is CallState.in_progress
    assert (await row(db, second)).state is CallState.dropped


async def test_a_malformed_twilio_body_on_one_call_does_not_stop_the_sweep(
    db, twilio, add_call
):
    fetch, _ = twilio
    fetch.side_effect = [KeyError("status"), ("completed", None)]
    first = await add_call(twilio_call_id="CA1")
    second = await add_call(twilio_call_id="CA2")
    first, second = sorted((first, second), key=lambda c: c.id)

    assert await sweep(NOW) == 1

    assert (await row(db, first)).state is CallState.in_progress
    assert (await row(db, second)).state is CallState.dropped


async def test_a_voicemail_whose_callback_was_lost_ends_unanswered(
    db, twilio, add_call
):
    fetch, _ = twilio
    fetch.return_value = ("completed", "machine_end_beep")
    call = await add_call(twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    assert (await row(db, call)).state is CallState.unanswered
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert redial.attempt == 2 and redial.state is CallState.queued


async def test_a_sid_twilio_does_not_know_fails(db, twilio, add_call):
    fetch, _ = twilio
    request = httpx.Request("GET", "https://api.twilio.com/x")
    fetch.side_effect = httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(404, request=request)
    )
    call = await add_call(state=CallState.ringing, twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    assert (await row(db, call)).state is CallState.failed
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert redial.attempt == 2 and redial.state is CallState.queued


async def test_an_answered_call_twilio_does_not_know_drops(db, twilio, add_call):
    fetch, _ = twilio
    request = httpx.Request("GET", "https://api.twilio.com/x")
    fetch.side_effect = httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(404, request=request)
    )
    call = await add_call(state=CallState.in_progress, twilio_call_id="CA1")

    assert await sweep(NOW) == 1

    assert (await row(db, call)).state is CallState.dropped
    assert await db.scalar(select(Call).where(Call.previous_call_id == call.id)) is None
