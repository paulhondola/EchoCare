"""What a picked-up call is answered with, and the notes from past calls (04 §5,
design §5 A)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update

from app.calls import service
from app.calls.service import answer_context
from app.medical.models import MedicalRecord, MedicalRecordState
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
    context = await answer_context(db, (await a_call(db, senior)).id, notes=True)
    assert context.follow_up == FIRST
    assert context.how_to_talk == ("Vorbiți rar",)
    assert SECOND not in repr(context)


async def test_context_never_carries_trends_or_narrative(db, senior):
    await a_summary(db, senior, content(FIRST))
    call = await a_call(db, senior)
    context = await answer_context(db, call.id, notes=True)
    assert NARRATIVE not in repr(context) and TREND not in repr(context)
    agent = agent_for(call.id, context)(AsyncMock())
    instructions = agent.history[0].parts[0].content
    assert NARRATIVE not in instructions and TREND not in instructions
    assert FIRST in instructions


async def test_unreadable_content_gives_no_notes(db, senior):
    await a_summary(db, senior, {"narrative": 5})
    context = await answer_context(db, (await a_call(db, senior)).id, notes=True)
    assert (context.follow_up, context.how_to_talk) == (None, ())


async def test_a_welcome_call_gets_no_notes(db, senior):
    await a_summary(db, senior, content(FIRST))
    context = await answer_context(
        db, (await a_call(db, senior, "welcome")).id, notes=True
    )
    assert (context.follow_up, context.how_to_talk) == (None, ())


async def test_a_failed_summary_read_gives_no_notes(db, senior, monkeypatch, caplog):
    await a_summary(db, senior, content(FIRST))
    call = await a_call(db, senior)
    monkeypatch.setattr(
        service, "latest_summary", AsyncMock(side_effect=RuntimeError("secret words"))
    )
    context = await answer_context(db, call.id, notes=True)
    assert context.greeting and (context.follow_up, context.how_to_talk) == (None, ())
    assert f"summary read failed, call {call.id}: RuntimeError" in caplog.text
    assert "secret words" not in caplog.text


async def test_the_answer_path_reads_no_summary(db, senior, monkeypatch):
    await a_summary(db, senior, content(FIRST))
    read = AsyncMock()
    monkeypatch.setattr(service, "latest_summary", read)
    context = await answer_context(db, (await a_call(db, senior)).id)
    read.assert_not_awaited()
    assert (context.follow_up, context.how_to_talk) == (None, ())


async def a_record(db, senior, state=MedicalRecordState.confirmed) -> None:
    def item(n, included=True):
        return {
            "condition": "c",
            "question": f"Întrebarea {n}?",
            "worrying": f"îngrijorător {n}",
            "evidence": "e",
            "included": included,
        }

    db.add(
        MedicalRecord(
            senior_id=senior.id,
            storage_key="k",
            uploaded_by=senior.medic_id,
            state=state,
            items=[item(1), item(2, False), item(3)],
        )
    )
    await db.commit()


async def test_context_rotates_through_confirmed_checks(db, senior):
    await a_record(db, senior)
    call = await a_call(db, senior)
    first = await answer_context(db, call.id, notes=True)
    assert first.medical_check == ("Întrebarea 1?", "îngrijorător 1")
    call.state = "completed"
    await db.commit()
    second = await answer_context(db, (await a_call(db, senior)).id, notes=True)
    assert second.medical_check == ("Întrebarea 3?", "îngrijorător 3")


async def test_unanswered_calls_do_not_advance_the_check(db, senior):
    await a_record(db, senior)
    await a_call(db, senior, state="unanswered")
    context = await answer_context(db, (await a_call(db, senior)).id, notes=True)
    assert context.medical_check[0] == "Întrebarea 1?"


async def test_context_has_no_check_for_a_welcome_call_or_unconfirmed_record(
    db, senior
):
    await a_record(db, senior, MedicalRecordState.review)
    context = await answer_context(
        db, (await a_call(db, senior, state="unanswered")).id, notes=True
    )
    assert context.medical_check is None
    await db.execute(update(MedicalRecord).values(state=MedicalRecordState.confirmed))
    await db.commit()
    welcome = await answer_context(
        db, (await a_call(db, senior, "welcome")).id, notes=True
    )
    assert welcome.medical_check is None


async def test_context_without_notes_reads_no_check(db, senior):
    await a_record(db, senior)
    context = await answer_context(db, (await a_call(db, senior)).id)
    assert context.medical_check is None


async def test_the_check_reaches_the_agent_prompt(db, senior):
    await a_record(db, senior)
    call = await a_call(db, senior)
    context = await answer_context(db, call.id, notes=True)
    agent = agent_for(call.id, context)(AsyncMock())
    assert "Întrebarea 1?" in agent.history[0].parts[0].content


async def test_a_failed_check_read_keeps_the_summary(db, senior, monkeypatch, caplog):
    await a_summary(db, senior, content(FIRST))
    call = await a_call(db, senior)
    monkeypatch.setattr(
        service, "confirmed_checks", AsyncMock(side_effect=RuntimeError("secret words"))
    )
    context = await answer_context(db, call.id, notes=True)
    assert context.follow_up == FIRST and context.medical_check is None
    assert f"medical check read failed, call {call.id}: RuntimeError" in caplog.text
    assert "secret words" not in caplog.text
