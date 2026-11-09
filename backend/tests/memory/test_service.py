"""Which calls are summarized, and the tasks that write them (#63, design §4)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy import func, select

from app.core.db import Session
from app.core.settings import get_settings
from app.memory import service
from app.memory.service import ATTEMPTS, due_calls, start_summaries, write_summary
from app.memory.writer import summary_agent
from app.models import (
    Call,
    CallTrigger,
    CallTurn,
    EnrollmentState,
    Speaker,
    SummaryVersion,
    TurnKind,
)
from app.seniors.schemas import SummaryContent
from app.seniors.service import add_summary
from app.status.engine import Severity
from app.voice.calls import CallState

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
SAID = "Mi-e cam frig acasă"


@pytest.fixture(autouse=True)
def fresh_state():
    service._running.clear()
    service._failures.clear()
    yield
    service._running.clear()
    service._failures.clear()


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior("+40700000111")


async def add_call(
    db,
    senior,
    *,
    ended=timedelta(hours=1),
    trigger=CallTrigger.campaign,
    state=CallState.completed,
    turns=(),
) -> Call:
    call = Call(
        senior_id=senior.id,
        trigger=trigger,
        starting_severity=Severity.green,
        state=state,
        due_at=NOW - timedelta(days=2),
        started_at=NOW - ended - timedelta(minutes=1),
        ended_at=NOW - ended,
    )
    db.add(call)
    await db.flush()
    for i, (speaker, text, age) in enumerate(turns):
        db.add(
            CallTurn(
                call_id=call.id,
                position=i,
                speaker=speaker,
                kind=TurnKind.speech,
                content=text,
                at=NOW - age,
            )
        )
    await db.commit()
    return call


def output(call: Call) -> dict:
    cited = {
        "topic": "frig",
        "question": "E cald acum?",
        "call_id": str(call.id),
        "quote": SAID,
    }
    return {
        "follow_ups": [cited],
        "how_to_talk": [],
        "trends": [],
        "narrative": "Se plânge de frig.",
    }


def agent_says(monkeypatch, call: Call):
    model = TestModel(custom_output_args=output(call))
    monkeypatch.setattr(service, "summary_agent", lambda _: summary_agent(model))
    return model


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")


async def run_tasks():
    await asyncio.gather(*service._running.values(), return_exceptions=True)
    await asyncio.sleep(0)  # the done-callbacks


async def due(db) -> list:
    return await due_calls(db, NOW)


async def test_a_completed_campaign_call_is_due(db, senior):
    call = await add_call(db, senior)
    assert await due(db) == [call.id]


@pytest.mark.parametrize(
    "columns",
    [
        {"trigger": CallTrigger.test},
        {"trigger": CallTrigger.welcome},
        {"state": CallState.unanswered},
        {"state": CallState.failed},
        {"ended": timedelta(hours=25)},
        {"older_than_latest": True},
    ],
    ids=["test", "welcome", "unanswered", "failed", "25h", "older-than-latest"],
)
async def test_skipped_calls(db, senior, columns):
    older = columns.pop("older_than_latest", False)
    if older:
        latest = await add_call(db, senior, ended=timedelta(hours=1))
        add_summary(
            db,
            senior_id=senior.id,
            call_id=latest.id,
            previous_id=None,
            content=SummaryContent(
                follow_ups=[], how_to_talk=[], trends=[], narrative="n"
            ),
            model="m",
        )
        await db.commit()
        columns["ended"] = timedelta(hours=2)
    await add_call(db, senior, **columns)
    assert await due(db) == []


@pytest.mark.parametrize(("age", "is_due"), [(1, False), (3, True)])
async def test_a_handed_over_call_waits_for_the_das_talk(db, senior, age, is_due):
    call = await add_call(
        db,
        senior,
        state=CallState.handed_over,
        turns=[(Speaker.das, "Bună ziua", timedelta(minutes=age))],
    )
    assert await due(db) == ([call.id] if is_due else [])


async def test_a_withdrawn_senior_is_not_summarized(db, senior):
    await add_call(db, senior)
    senior.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    assert await due(db) == []


async def test_a_seniors_calls_are_summarized_in_order(db, senior, monkeypatch, keyed):
    first = await add_call(
        db,
        senior,
        ended=timedelta(hours=3),
        turns=[(Speaker.senior, SAID, timedelta(hours=3))],
    )
    second = await add_call(
        db,
        senior,
        ended=timedelta(hours=1),
        turns=[(Speaker.senior, SAID, timedelta(hours=1))],
    )
    agent_says(monkeypatch, first)
    assert await start_summaries(NOW) == 1
    assert await start_summaries(NOW) == 0  # the senior's task is still running
    await run_tasks()
    agent_says(monkeypatch, second)
    assert await start_summaries(NOW) == 1
    await run_tasks()
    versions = {v.call_id: v for v in (await db.scalars(select(SummaryVersion))).all()}
    assert versions[second.id].previous_id == versions[first.id].id
    assert versions[first.id].previous_id is None


async def test_a_failing_call_is_tried_three_times(db, senior, monkeypatch, keyed):
    call = await add_call(
        db, senior, turns=[(Speaker.senior, SAID, timedelta(hours=1))]
    )
    monkeypatch.setattr(service, "write_summary", _boom)
    for _ in range(ATTEMPTS):
        assert await start_summaries(NOW) == 1
        await run_tasks()
    assert service._failures[call.id] == ATTEMPTS
    assert await due(db) == []


async def test_no_key_starts_nothing(db, senior, monkeypatch):
    await add_call(db, senior, turns=[(Speaker.senior, SAID, timedelta(hours=1))])
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "")
    assert await start_summaries(NOW) == 0
    assert service._running == {} and not service._failures


async def _boom(call_id):
    raise RuntimeError("model down")


async def test_a_second_copy_writing_the_same_call_is_a_no_op(db, senior):
    call = await add_call(
        db, senior, turns=[(Speaker.senior, SAID, timedelta(hours=1))]
    )
    model = TestModel(custom_output_args=output(call))
    await write_summary(call.id, model=model)
    await write_summary(call.id, model=model)
    async with Session() as s:
        assert await s.scalar(select(func.count()).select_from(SummaryVersion)) == 1


async def test_logs_name_no_words(db, senior, monkeypatch, caplog, keyed):
    secret = "cuvinte-secrete"
    call = await add_call(
        db, senior, turns=[(Speaker.senior, secret, timedelta(hours=1))]
    )
    # A quote that is not in the call: the agent fails after its retries.
    monkeypatch.setattr(
        service,
        "summary_agent",
        lambda _: summary_agent(TestModel(custom_output_args=output(call))),
    )
    with caplog.at_level(logging.INFO, logger="echocare.memory"):
        await start_summaries(NOW)
        await run_tasks()
    failed = [r for r in caplog.records if "summary failed" in r.getMessage()]
    assert len(failed) == 1
    text = failed[0].getMessage()
    assert str(call.id) in text and "UnexpectedModelBehavior" in text
    assert secret not in caplog.text and SAID not in caplog.text
