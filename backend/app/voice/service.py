import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import object_session

from app.core.changes import Change, ChangeKind, note
from app.core.db import Session
from app.core.settings import get_settings
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

log = logging.getLogger("echocare.voice")


def _note_moved(session: AsyncSession | OrmSession | None, call: Call) -> None:
    """A scripted test call is counted by no rule (05 §1) and left out of the history,
    so it tells nobody either."""
    if call.trigger != CallTrigger.test:
        note(session, Change(ChangeKind.call_moved, call.senior_id))


async def transition(
    session: AsyncSession,
    call_id: uuid.UUID,
    sid: str | None,
    new: CallState | None,
    *,
    only_from: CallState | None = None,
) -> CallState | None:
    """Applies a callback to the call record; the state it moved to, or None (03 §9).

    The row is locked, so a status callback and voicemail detection arriving together
    apply one after the other. With `only_from`, nothing moves unless the locked row is
    in that state: a sweep acts on what it read, not on what the call became since.
    Doesn't commit: `move_call` and `settle` do.
    """
    call = await session.scalar(
        select(Call).where(Call.id == call_id).with_for_update()
    )
    if call is None:
        log.warning("callback for unknown call %s", call_id)
        return None
    if call.twilio_call_id is None and sid:
        call.twilio_call_id = sid  # the callback can beat the dial's own answer
    if only_from is not None and call.state != only_from:
        return None
    moved = after_callback(call.state, new)
    if moved is not None:
        log.info("call %s: %s -> %s", call_id, call.state, moved)
        stamp(call, moved, datetime.now(UTC))
        call.state = moved
        _note_moved(session, call)
    elif new is not None and new is not call.state:
        log.info("call %s: %s ignored in %s", call_id, new, call.state)
    return moved


async def move_call(
    session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None
) -> CallState | None:
    """`transition`, committed, for a move that needs no more (04 §4.2)."""
    moved = await transition(session, call_id, sid, new)
    await session.commit()
    return moved


async def live_call_for_update(
    session: AsyncSession, call_id: uuid.UUID
) -> Call | None:
    """The call while it is in progress, locked until the caller's transaction ends, so
    two answers for one call apply one after the other; None otherwise."""
    return await session.scalar(
        select(Call)
        .where(Call.id == call_id, Call.state == CallState.in_progress)
        .with_for_update()
    )


async def answer_handover(
    session: AsyncSession, call_id: uuid.UUID, answered: bool
) -> Call | None:
    """Whether DAS picked up the hand-over (05 §1). An answer always counts; a later
    "not answered" doesn't undo one. Doesn't commit."""
    call = await session.scalar(
        select(Call).where(Call.id == call_id).with_for_update()
    )
    if call is not None and (answered or call.handover_answered is None):
        call.handover_answered = answered
    return call


async def call_in_progress(session: AsyncSession, senior_id: uuid.UUID) -> bool:
    """Whether one of the senior's calls is ringing or live, for the badge (UC-12)."""
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Call.senior_id == senior_id,
                    Call.state.in_([CallState.ringing, CallState.in_progress]),
                    Call.trigger != CallTrigger.test,
                )
            )
        )
    )


async def form_of_address(session: AsyncSession, call_id: uuid.UUID) -> str | None:
    """How the call greets its senior; None for an unknown call (04 §4.2)."""
    return await session.scalar(
        select(Senior.form_of_address)
        .join(Call, Call.senior_id == Senior.id)
        .where(Call.id == call_id)
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
    starting_severity: Severity = Severity.green,
) -> None:
    """Queues a first attempt, starting green unless `starting_severity` says otherwise,
    for each senior the `seniors` condition picks; it may correlate with `Senior.id`.

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
                literal(starting_severity, Call.starting_severity.type),
                literal(CallState.queued, Call.state.type),
                literal(due_at, Call.due_at.type),
            ).where(seniors),
        )
        .on_conflict_do_nothing()
    )


def cooldown() -> timedelta:
    """How long after a call ended a new event attaches to it instead of starting a
    call (06 §3)."""
    return timedelta(seconds=30) if get_settings().demo_mode else timedelta(minutes=10)


async def recent_call(
    session: AsyncSession, senior_id: uuid.UUID, now: datetime
) -> Call | None:
    """The senior's call a new event attaches to: one queued or live, or one that ended
    within the cooldown (04 §3). A canceled call never took place."""
    return await session.scalar(
        select(Call)
        .where(
            Call.senior_id == senior_id,
            or_(
                Call.state.in_(LIVE),
                (Call.state != CallState.canceled)
                & (Call.ended_at >= now - cooldown()),
            ),
        )
        .order_by(Call.created_at.desc())
        .limit(1)
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
    A dialed call (`dialed_at` set) is left alone: Twilio's callback settles it.
    """
    await session.execute(
        update(Call)
        .where(Call.state == CallState.queued, Call.dialed_at.is_(None), which)
        .values(state=CallState.canceled, ended_at=now)
    )


async def take_for_dialing(
    session: AsyncSession, call_id: uuid.UUID, now: datetime
) -> bool:
    """Marks a queued call as handed to Twilio (`dialed_at`), only if nobody did first;
    whether this caller got it. The scheduler commits this before it dials, so a call is
    dialed once at most (06 §1). Doesn't commit.
    """
    taken = await session.scalar(
        update(Call)
        .where(Call.id == call_id, Call.state == CallState.queued)
        .where(Call.dialed_at.is_(None))
        .values(dialed_at=now)
        .returning(Call.id)
    )
    return taken is not None


async def store_sid(session: AsyncSession, call_id: uuid.UUID, sid: str) -> None:
    """Twilio's id for a dialed call, unless a status callback stored it first. Doesn't
    commit."""
    await session.execute(
        update(Call)
        .where(Call.id == call_id, Call.twilio_call_id.is_(None))
        .values(twilio_call_id=sid)
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
    changes nothing. A Twilio callback, which may skip ahead, uses `transition`."""
    if new == call.state:
        return
    call.state = advance(call.state, new)
    stamp(call, new, now)
    _note_moved(object_session(call), call)


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
    *,
    confidence: float | None = None,
) -> None:
    """One transcript row: an utterance or a key press (05 §1)."""
    session.add(
        CallTurn(
            call_id=call_id,
            position=position,
            speaker=speaker,
            kind=kind,
            content=content,
            confidence=confidence,
        )
    )


async def append_turn(
    session: AsyncSession,
    call_id: uuid.UUID,
    speaker: Speaker,
    kind: TurnKind,
    content: str,
    *,
    confidence: float | None = None,
) -> bool:
    """One transcript row after the call's last, for the callbacks that write turns with
    no relay session: the welcome call and the hand-over (05 §1). Locks the call row, so
    two callbacks at once never take one position. False for an unknown call. Doesn't
    commit."""
    if (
        await session.scalar(
            select(Call.id).where(Call.id == call_id).with_for_update()
        )
        is None
    ):
        return False
    position = await session.scalar(
        select(func.coalesce(func.max(CallTurn.position) + 1, 0)).where(
            CallTurn.call_id == call_id
        )
    )
    add_turn(session, call_id, position, speaker, kind, content, confidence=confidence)
    return True


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
        return LiveCall(row.twilio_call_id, row.form_of_address)


async def save_turn(
    call_id: uuid.UUID, speaker: Speaker, kind: TurnKind, content: str
) -> None:
    """One transcript row, committed as it comes, so a lost line keeps what was said
    (06 §1). Positioned by `append_turn`, like the hand-over's callbacks, so a relay
    turn and a callback's never take one position."""
    async with Session() as session:
        await append_turn(session, call_id, speaker, kind, content)
        await session.commit()


async def end_completed(call_id: uuid.UUID) -> None:
    """Our side closed the call: it ends completed, even if they hang up during the
    goodbye (03 §9)."""
    async with Session() as session:
        await move_call(session, call_id, None, CallState.completed)
