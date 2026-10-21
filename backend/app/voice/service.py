import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import ColumnElement, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Session
from app.seniors.models import Senior
from app.status.engine import Certainty, Question, Severity
from app.voice.calls import ANSWERED, ENDED, LIVE, CallState, advance, after_callback
from app.voice.models import (
    Answer,
    Call,
    CallTrigger,
    CallTurn,
    Speaker,
    TurnKind,
    WelcomeOutcome,
)
from app.voice.twilio import hang_up

log = logging.getLogger("echocare.voice")


async def transition(
    session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None
) -> CallState | None:
    """Applies a callback to the call record; the state it moved to, or None (03 §9).

    The row is locked, so a status callback and voicemail detection arriving together
    apply one after the other. Doesn't commit: `move_call` does, for the callbacks.
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
        log.info("call %s: %s -> %s", call_id, call.state, moved)
        stamp(call, moved, datetime.now(UTC))
        call.state = moved
    elif new is not None and new is not call.state:
        log.info("call %s: %s ignored in %s", call_id, new, call.state)
    return moved


async def move_call(
    session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None
) -> CallState | None:
    """`transition`, committed: the Twilio callbacks' way in (04 §4.2)."""
    moved = await transition(session, call_id, sid, new)
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
    seniors: ColumnElement[bool],
    *,
    trigger: CallTrigger,
    due_at: datetime,
    campaign_id: uuid.UUID | None = None,
) -> None:
    """Queues a first attempt, starting green, for each senior the `seniors` condition
    picks; it may correlate with `Senior.id`.

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
            select(
                Senior.id,
                literal(trigger, Call.trigger.type),
                literal(campaign_id, Call.campaign_id.type),
                literal(1, Call.attempt.type),
                literal(Severity.green, Call.starting_severity.type),
                literal(CallState.queued, Call.state.type),
                literal(due_at, Call.due_at.type),
            ).where(seniors),
        )
        .on_conflict_do_nothing()
    )


def queue_redial(session: AsyncSession, call: Call, due_at: datetime) -> None:
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
    session: AsyncSession, which: ColumnElement[bool], *, now: datetime
) -> None:
    """Cancels the queued calls `which` picks: a lapsed or ended campaign's, a
    withdrawn senior's (03 §9). The condition is required: none would cancel them all.
    `queued -> canceled` is an allowed move (03 §9), and the state filter is its guard.
    """
    await session.execute(
        update(Call)
        .where(Call.state == CallState.queued, which)
        .values(state=CallState.canceled, ended_at=now)
    )


# A call's progress, transcript and answers, for the mock and the agent (ADR-005).


def stamp(call: Call, state: CallState, now: datetime) -> None:
    """The times a move into `state` sets: picked up, the first time, and ended (03 §9)."""
    if call.started_at is None and state in ANSWERED:
        call.started_at = now
    if state in ENDED:
        call.ended_at = now


def advance_call(call: Call, new: CallState, now: datetime) -> None:
    """One allowed step of the call's lifecycle, stamped (03 §9); the same state again
    changes nothing. A Twilio callback, which may skip ahead, uses `move_call`."""
    if new == call.state:
        return
    call.state = advance(call.state, new)
    stamp(call, new, now)


def finish(
    call: Call,
    state: CallState,
    now: datetime,
    *,
    final_severity: Severity | None = None,
    final_certainty: Certainty | None = None,
    reason: str | None = None,
    summary: str | None = None,
    welcome_outcome: WelcomeOutcome | None = None,
) -> None:
    """Ends the call in `state` with its result; a field given as None stays as it is."""
    advance_call(call, state, now)
    result = {
        "final_severity": final_severity,
        "final_certainty": final_certainty,
        "reason": reason,
        "summary": summary,
        "welcome_outcome": welcome_outcome,
    }
    for field, value in result.items():
        if value is not None:
            setattr(call, field, value)


def add_turn(
    session: AsyncSession,
    call_id: uuid.UUID,
    position: int,
    speaker: Speaker,
    kind: TurnKind,
    content: str,
) -> None:
    """One transcript row: an utterance or a key press (05 §1)."""
    session.add(
        CallTurn(
            call_id=call_id,
            position=position,
            speaker=speaker,
            kind=kind,
            content=content,
        )
    )


def record_answer(
    session: AsyncSession,
    call_id: uuid.UUID,
    field: Question,
    value: str,
    *,
    clear: bool,
    quote: str,
    at: datetime,
) -> None:
    """What the call heard for one of the three questions (03 §3)."""
    session.add(
        Answer(
            call_id=call_id, field=field, value=value, clear=clear, quote=quote, at=at
        )
    )


# The agent's way in (ADR-005 §6). Unlike the functions above, each opens and commits
# its own session: the call session holds none, so it can leave the process (ADR-004).


@dataclass(frozen=True)
class LiveCall:
    """What a relay session needs of its call (04 §4.3)."""

    twilio_call_id: str | None
    form_of_address: str
    # Where the transcript goes on: 0 for a new call, after the last turn when Twilio
    # reconnects the same call.
    next_position: int


async def open_line(call_id: uuid.UUID) -> LiveCall | None:
    """The call while it is live; None once it has ended, or for an unknown id, so a
    relay connect is one-time (01 §4 channel 7)."""
    async with Session() as session:
        row = (
            await session.execute(
                select(Call.twilio_call_id, Senior.form_of_address)
                .join(Senior, Senior.id == Call.senior_id)
                .where(Call.id == call_id, Call.state.in_(LIVE))
            )
        ).first()
        if row is None:
            return None
        position = await session.scalar(
            select(func.coalesce(func.max(CallTurn.position) + 1, 0)).where(
                CallTurn.call_id == call_id
            )
        )
        return LiveCall(row.twilio_call_id, row.form_of_address, position)


async def save_turn(
    call_id: uuid.UUID, position: int, speaker: Speaker, kind: TurnKind, content: str
) -> None:
    """One transcript row, committed as it comes, so a lost line keeps what was said
    (06 §1)."""
    async with Session() as session:
        add_turn(session, call_id, position, speaker, kind, content)
        await session.commit()


async def end_completed(call_id: uuid.UUID) -> None:
    """Our side closed the call: it ends completed, even if they hang up during the
    goodbye (03 §9)."""
    async with Session() as session:
        await move_call(session, call_id, None, CallState.completed)
