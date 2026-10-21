"""The call-lifecycle functions other packages write `calls` through (ADR-005)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Call, CallTrigger, Senior
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.service import cancel_queued, queue_calls, queue_redial

NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)


def a_call(senior: Senior, **columns) -> Call:
    return Call(
        senior_id=senior.id,
        starting_severity=Severity.green,
        due_at=NOW,
        **{"trigger": CallTrigger.manual, **columns},
    )


async def test_queue_calls_skips_a_senior_with_a_live_call(db, add_senior):
    busy, free = await add_senior("+40700000101"), await add_senior("+40700000102")
    db.add(a_call(busy))
    await db.commit()
    await queue_calls(
        db,
        select(Senior.id).where(Senior.id.in_([busy.id, free.id])),
        trigger=CallTrigger.campaign,
        due_at=NOW,
    )
    await db.commit()
    rows = (await db.execute(select(Call.senior_id, Call.trigger))).all()
    assert sorted(rows) == sorted(
        [(busy.id, CallTrigger.manual), (free.id, CallTrigger.campaign)]
    )


async def test_a_redial_that_collides_raises(db, add_senior):
    senior = await add_senior("+40700000101")
    first = a_call(senior, trigger=CallTrigger.campaign, state=CallState.unanswered)
    db.add_all([first, a_call(senior)])
    await db.commit()
    await queue_redial(db, first, NOW)
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_cancel_queued_leaves_other_states_alone(db, add_senior):
    a, b = await add_senior("+40700000101"), await add_senior("+40700000102")
    queued, talking = a_call(a), a_call(b, state=CallState.in_progress)
    db.add_all([queued, talking])
    await db.commit()
    await cancel_queued(db, Call.senior_id.in_([a.id, b.id]), now=NOW)
    await db.commit()
    await db.refresh(queued)
    await db.refresh(talking)
    assert (queued.state, queued.ended_at) == (CallState.canceled, NOW)
    assert (talking.state, talking.ended_at) == (CallState.in_progress, None)
