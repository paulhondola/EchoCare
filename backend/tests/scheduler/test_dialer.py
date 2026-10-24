from datetime import UTC, datetime, timedelta
from itertools import count
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from app.core.settings import get_settings
from app.models import Call, CallTrigger, EnrollmentState
from app.scheduler.dialer import dial_due
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.service import take_for_dialing

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
PHONE = "+40700000101"


@pytest.fixture(autouse=True)
def twilio(monkeypatch):
    """Twilio set up, everyone dialable, and a dial that answers with a sid."""
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", "AC1")
    monkeypatch.setattr(s, "twilio_auth_token", "token")
    monkeypatch.setattr(s, "twilio_from_number", "+40700000999")
    monkeypatch.setattr(s, "dial_allowlist", "*")
    monkeypatch.setattr(s, "max_live_calls", 3)
    dial = AsyncMock(side_effect=[f"CA{n}" for n in range(1, 10)])
    monkeypatch.setattr("app.scheduler.dialer.dial", dial)
    return dial


@pytest.fixture
def add_call(db, add_active_senior):
    """add_call(): a queued campaign call for a new active senior, due a minute ago."""
    numbers = count(110)

    async def add(phone: str | None = None, **columns) -> Call:
        senior = await add_active_senior(phone or f"+40700000{next(numbers)}")
        call = Call(
            **{
                "senior_id": senior.id,
                "trigger": CallTrigger.campaign,
                "starting_severity": Severity.green,
                "due_at": NOW - timedelta(minutes=1),
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


async def test_a_due_call_is_dialed_and_its_sid_stored(db, twilio, add_call):
    call = await add_call()

    assert await dial_due(NOW) == 1

    call = await row(db, call)
    assert call.dialed_at is not None and call.twilio_call_id == "CA1"
    assert call.state is CallState.queued  # Twilio's callback moves it on
    twilio.assert_awaited_once()
    assert twilio.await_args.args[1:] == (call.id, "answer")


async def test_a_call_not_yet_due_waits(db, twilio, add_call):
    await add_call(due_at=NOW + timedelta(minutes=5))

    assert await dial_due(NOW) == 0
    twilio.assert_not_awaited()


async def test_due_calls_go_in_id_order_up_to_the_free_lines(
    db, twilio, add_call, monkeypatch
):
    await add_call(state=CallState.ringing, dialed_at=NOW, twilio_call_id="CA0")
    calls = [await add_call() for _ in range(3)]

    assert await dial_due(NOW) == 2

    by_id = sorted(calls, key=lambda c: c.id)
    dialed = [(await row(db, c)).dialed_at is not None for c in by_id]
    assert dialed == [True, True, False]


async def test_a_dialed_call_is_never_dialed_again(db, twilio, add_call):
    call = await add_call()
    twilio.side_effect = httpx.ReadTimeout("x")

    assert await dial_due(NOW) == 0
    assert await dial_due(NOW) == 0

    twilio.assert_awaited_once()
    call = await row(db, call)
    assert call.state is CallState.queued
    assert call.dialed_at is not None and call.twilio_call_id is None


async def test_without_twilio_nothing_is_dialed(
    db, client, twilio, add_call, monkeypatch
):
    monkeypatch.setattr(get_settings(), "twilio_account_sid", "")
    call = await add_call()

    assert await dial_due(NOW) == 0

    twilio.assert_not_awaited()
    assert (await row(db, call)).dialed_at is None
    r = await client.get(
        "/api/profile/mock-call", headers={"Authorization": "Bearer +40700000110"}
    )
    assert r.json()["call_id"] == str(call.id)


async def test_the_allowlist_decides(db, client, twilio, add_call, monkeypatch):
    s = get_settings()
    call = await add_call()  # +40700000110
    monkeypatch.setattr(s, "dial_allowlist", "")
    assert await dial_due(NOW) == 0

    monkeypatch.setattr(s, "dial_allowlist", "+40700000999")
    assert await dial_due(NOW) == 0
    twilio.assert_not_awaited()
    r = await client.get(
        "/api/profile/mock-call", headers={"Authorization": "Bearer +40700000110"}
    )
    assert r.json()["call_id"] == str(call.id)  # the card stays

    monkeypatch.setattr(s, "dial_allowlist", "+40700000110")
    assert await dial_due(NOW) == 1


async def test_unlisted_calls_do_not_hold_the_free_lines(
    db, twilio, add_call, monkeypatch
):
    await add_call("+40700000201")  # the lower id, but not on the list
    listed = await add_call("+40700000202")
    monkeypatch.setattr(get_settings(), "max_live_calls", 1)
    monkeypatch.setattr(get_settings(), "dial_allowlist", "+40700000202")

    assert await dial_due(NOW) == 1
    assert (await row(db, listed)).dialed_at is not None


async def test_twilio_refusing_fails_the_call_and_queues_the_redial(
    db, twilio, add_call
):
    call = await add_call()
    response = httpx.Response(400, request=httpx.Request("POST", "https://t"))
    twilio.side_effect = httpx.HTTPStatusError(
        "bad", request=response.request, response=response
    )

    assert await dial_due(NOW) == 0

    assert (await row(db, call)).state is CallState.failed
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert redial.attempt == 2 and redial.state is CallState.queued


async def test_a_welcome_call_answers_at_the_welcome_address(db, twilio, add_senior):
    senior = await add_senior("+40700000150", enrollment_state=EnrollmentState.accepted)
    db.add(
        Call(
            senior_id=senior.id,
            trigger=CallTrigger.welcome,
            starting_severity=Severity.green,
            due_at=NOW,
        )
    )
    await db.commit()

    assert await dial_due(NOW) == 1
    assert twilio.await_args.args[2] == "welcome"


async def test_taking_a_call_for_dialing_works_once(db, add_call):
    call = await add_call()
    assert await take_for_dialing(db, call.id, NOW) is True
    assert await take_for_dialing(db, call.id, NOW) is False


async def test_a_canceled_call_or_one_already_stamped_is_not_taken(db, add_call):
    canceled = await add_call(state=CallState.canceled)
    stamped = await add_call(dialed_at=NOW)
    assert await take_for_dialing(db, canceled.id, NOW) is False
    assert await take_for_dialing(db, stamped.id, NOW) is False
