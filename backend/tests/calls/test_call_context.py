"""What a picked-up call is answered with, and the notes from past calls (04 §5,
design §5 A)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.calls import service
from app.calls.service import answer_context
from app.models import Call, SummaryVersion
from app.voice.router import agent_for

NARRATIVE = "NARATIUNE-UNICA-9 a avut o lună grea."
TREND = "TENDINTA-UNICA-7 somn mai slab"
FIRST = "Cum se simte genunchiul?"
SECOND = "A venit nepoata?"


async def a_call(db, senior, trigger="watch", state="in_progress") -> Call:
    call = Call(
        senior_id=senior.id,
        trigger=trigger,
        starting_severity="yellow",
        state=state,
        due_at=datetime.now(UTC),
    )
    db.add(call)
    await db.commit()
    return call


async def a_summary(db, senior, content: dict) -> None:
    past = await a_call(db, senior, state="completed")
    db.add(
        SummaryVersion(
            senior_id=senior.id, call_id=past.id, content=content, model="test"
        )
    )
    await db.commit()


def content(*questions: str, how=("Vorbiți rar",)) -> dict:
    cid = str(uuid.uuid4())
    quote = {"call_id": cid, "quote": "q"}
    return {
        "follow_ups": [
            {"topic": "t", "question": q, "call_id": cid, "quote": "q"}
            for q in questions
        ],
        "how_to_talk": list(how),
        "trends": [
            {
                "note": TREND,
                "direction": "worse",
                "evidence": [quote, quote],
            }
        ],
        "narrative": NARRATIVE,
    }


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior("+40700000101")


async def test_context_has_the_first_follow_up_only(db, senior):
    await a_summary(db, senior, content(FIRST, SECOND))
    context = await answer_context(db, (await a_call(db, senior)).id)
    assert context.follow_up == FIRST
    assert context.how_to_talk == ("Vorbiți rar",)
    assert SECOND not in repr(context)


async def test_context_never_carries_trends_or_narrative(db, senior):
    await a_summary(db, senior, content(FIRST))
    call = await a_call(db, senior)
    context = await answer_context(db, call.id)
    assert NARRATIVE not in repr(context) and TREND not in repr(context)
    agent = agent_for(call.id, context)(AsyncMock())
    assert NARRATIVE not in agent.history[0]["content"]
    assert TREND not in agent.history[0]["content"]
    assert FIRST in agent.history[0]["content"]


async def test_unreadable_content_gives_no_notes(db, senior):
    await a_summary(db, senior, {"narrative": 5})
    context = await answer_context(db, (await a_call(db, senior)).id)
    assert (context.follow_up, context.how_to_talk) == (None, ())


async def test_a_welcome_call_gets_no_notes(db, senior):
    await a_summary(db, senior, content(FIRST))
    context = await answer_context(db, (await a_call(db, senior, "welcome")).id)
    assert (context.follow_up, context.how_to_talk) == (None, ())


async def test_a_failed_summary_read_gives_no_notes(db, senior, monkeypatch, caplog):
    await a_summary(db, senior, content(FIRST))
    call = await a_call(db, senior)
    monkeypatch.setattr(
        service, "latest_summary", AsyncMock(side_effect=RuntimeError("secret words"))
    )
    context = await answer_context(db, call.id)
    assert context.greeting and (context.follow_up, context.how_to_talk) == (None, ())
    assert f"summary read failed, call {call.id}: RuntimeError" in caplog.text
    assert "secret words" not in caplog.text
