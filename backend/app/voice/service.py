import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import ColumnElement, Select, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.seniors.models import Senior
from app.status.engine import Severity
from app.voice.calls import ANSWERED, ENDED, CallState, advance, after_callback
from app.voice.models import Call, CallTrigger
from app.voice.twilio import hang_up

log = logging.getLogger("echocare.voice")


async def move_call(
    session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None
) -> CallState | None:
    """Applies a callback to the call record; the state it moved to, or None (03 §9).

    The row is locked, so a status callback and voicemail detection arriving together
    apply one after the other.
    """
    call = await session.scalar(
        select(Call).where(Call.id == call_id).with_for_update()
    )
    if call is None:
        log.warning("callback for unknown call %s", call_id)
        return None
    if call.twilio_call_id is None and sid:
        call.twilio_call_id = sid  # the callback can beat the dial's own answer
    moved = after_callback(call.state, new)
    if moved is not None:
        now = datetime.now(UTC)
        if call.started_at is None and moved in ANSWERED:
            call.started_at = now
        if moved in ENDED:
            call.ended_at = now
        log.info("call %s: %s -> %s", call_id, call.state, moved)
        call.state = moved
    elif new is not None and new is not call.state:
        log.info("call %s: %s ignored in %s", call_id, new, call.state)
    await session.commit()
    return moved


async def form_of_address(session: AsyncSession, call_id: uuid.UUID) -> str | None:
    """How the call greets its senior; None for an unknown call (04 §4.2)."""
    return await session.scalar(
        select(Senior.form_of_address)
        .join(Call, Call.senior_id == Senior.id)
        .where(Call.id == call_id)
    )


async def machine_answered(
    session: AsyncSession, call_id: uuid.UUID, sid: str | None
) -> None:
    """A machine picked up: the call ends unanswered and we hang up (04 §4.2)."""
    moved = await move_call(session, call_id, sid, CallState.unanswered)
    if moved is CallState.unanswered and sid:
        try:
            await hang_up(sid)
        except httpx.HTTPError:
            log.warning(
                "call %s: could not hang up on the machine", call_id, exc_info=True
            )


# The call rows' writes for other packages (ADR-005): queueing, redialing and canceling.
# None of these commits.


async def queue_calls(
    session: AsyncSession,
    senior_ids: Select,
    *,
    trigger: CallTrigger,
    due_at: datetime,
    campaign_id: uuid.UUID | None = None,
) -> None:
    """Queues a first attempt, starting green, for each senior `senior_ids` selects.

    A senior who already has a live call is skipped by `uq_calls_live_senior` (05 §3),
    so nobody gets two.
    """
    await session.execute(
        insert(Call)
        .from_select(
            [
                Call.senior_id,
                Call.trigger,
                Call.campaign_id,
                Call.attempt,
                Call.starting_severity,
                Call.state,
                Call.due_at,
            ],
            senior_ids.add_columns(
                literal(trigger, Call.trigger.type),
                literal(campaign_id, Call.campaign_id.type),
                literal(1, Call.attempt.type),
                literal(Severity.green, Call.starting_severity.type),
                literal(CallState.queued, Call.state.type),
                literal(due_at, Call.due_at.type),
            ),
        )
        .on_conflict_do_nothing()
    )


async def queue_redial(session: AsyncSession, call: Call, due_at: datetime) -> None:
    """The attempt after `call`, its own record pointing back to it (03 §9).

    No conflict clause, unlike `queue_calls`: a redial that meets a live call for the
    same senior raises instead of vanishing (design §6.5).
    """
    session.add(
        Call(
            senior_id=call.senior_id,
            trigger=call.trigger,
            campaign_id=call.campaign_id,
            previous_call_id=call.id,
            attempt=call.attempt + 1,
            starting_severity=call.starting_severity,
            due_at=due_at,
        )
    )


async def cancel_queued(
    session: AsyncSession, *where: ColumnElement[bool], now: datetime
) -> None:
    """Cancels the queued calls `where` picks: a lapsed or ended campaign's, a
    withdrawn senior's (03 §9)."""
    await session.execute(
        update(Call)
        .where(Call.state == CallState.queued, *where)
        .values(state=advance(CallState.queued, CallState.canceled), ended_at=now)
    )
