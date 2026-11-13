import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.db import engine
from app.core.settings import get_settings
from app.main import app
from app.memory import service
from app.models import (
    Call,
    CallTrigger,
    Campaign,
    CampaignKind,
    Role,
    WarningLevel,
)
from app.scheduler.loop import LOCK, tick
from app.status.engine import Severity
from app.voice.calls import CallState

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def patch_steps(monkeypatch, **overrides):
    """The tick's six steps, patched where the loop uses them."""
    steps = {
        "cancel_lapsed": AsyncMock(),
        "dial_due": AsyncMock(return_value=0),
        "sweep": AsyncMock(return_value=0),
        "silence_watches": AsyncMock(return_value=0),
        "prune_watch_readings": AsyncMock(return_value=0),
        "start_summaries": AsyncMock(return_value=0),
        "start_analyses": AsyncMock(return_value=0),
        **overrides,
    }
    for name, step in steps.items():
        monkeypatch.setattr(f"app.scheduler.loop.{name}", step)
    return steps


async def test_two_schedulers_one_tick(db, monkeypatch):
    steps = patch_steps(monkeypatch)
    async with engine.connect() as other:
        await other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK})
        try:
            assert await tick(NOW) is False
            steps["dial_due"].assert_not_called()
        finally:
            await other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK})
    assert await tick(NOW) is True
    steps["dial_due"].assert_awaited_once_with(NOW)


async def test_a_step_that_raises_does_not_stop_the_others(db, monkeypatch):
    steps = patch_steps(monkeypatch, dial_due=AsyncMock(side_effect=RuntimeError))
    assert await tick(NOW) is True
    steps["sweep"].assert_awaited_once_with(NOW)
    steps["silence_watches"].assert_awaited_once()
    steps["prune_watch_readings"].assert_awaited_once()


async def test_the_tick_cancels_a_lapsed_campaigns_calls(
    db, add_user, add_active_senior, monkeypatch
):
    for name in (
        "dial_due",
        "sweep",
        "silence_watches",
        "start_summaries",
        "start_analyses",
    ):
        monkeypatch.setattr(f"app.scheduler.loop.{name}", AsyncMock(return_value=0))
    das = await add_user("+40700000001", Role.das)
    senior = await add_active_senior("+40700000101")
    campaign = Campaign(
        kind=CampaignKind.heat,
        level=WarningLevel.yellow,
        started_by=das.id,
        warning_until=NOW - timedelta(hours=1),
    )
    db.add(campaign)
    await db.flush()
    call = Call(
        senior_id=senior.id,
        campaign_id=campaign.id,
        trigger=CallTrigger.campaign,
        starting_severity=Severity.green,
        due_at=NOW - timedelta(hours=2),
    )
    db.add(call)
    await db.commit()

    assert await tick(NOW) is True

    state = await db.scalar(select(Call.state).where(Call.id == call.id))
    assert state == CallState.canceled


def test_the_lifespan_starts_no_loop_in_tests(monkeypatch):
    run = Mock(side_effect=AssertionError("the loop must not start"))
    monkeypatch.setattr("app.main.run", run)
    with TestClient(app):
        pass
    run.assert_not_called()


async def test_the_tick_never_waits_for_a_summary(db, add_active_senior, monkeypatch):
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")
    """A summary's model call runs in its own task, so the lock is free after the tick."""
    for name in ("cancel_lapsed", "dial_due", "sweep", "silence_watches"):
        monkeypatch.setattr(f"app.scheduler.loop.{name}", AsyncMock(return_value=0))
    senior = await add_active_senior("+40700000102")
    db.add(
        Call(
            senior_id=senior.id,
            trigger=CallTrigger.watch,
            starting_severity=Severity.green,
            state=CallState.completed,
            due_at=NOW,
            ended_at=NOW - timedelta(minutes=5),
        )
    )
    await db.commit()
    never = asyncio.Event()
    started = asyncio.Event()

    async def stuck(call_id):
        started.set()
        await never.wait()

    monkeypatch.setattr("app.memory.service.write_summary", stuck)
    try:
        assert await asyncio.wait_for(tick(NOW), 5) is True
        await asyncio.wait_for(started.wait(), 5)
        async with engine.connect() as other:
            free = await other.scalar(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK}
            )
            assert free
            await other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK})
    finally:
        for task in service._running.values():
            task.cancel()
        await asyncio.gather(*service._running.values(), return_exceptions=True)
        service._running.clear()
