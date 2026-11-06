import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse
from app.calls.schemas import AnswerView, CallSummary, TranscriptDetail
from app.campaigns.models import Campaign
from app.codes.models import StatusReport
from app.incidents.schemas import ReportView, TurnView
from app.incidents.service import call_detail
from app.seniors.models import Senior
from app.seniors.service import reach, reach_senior
from app.voice.calls import CallState
from app.voice.dialogue import wellbeing_greeting
from app.voice.models import Answer, Call, CallTrigger, CallTurn
from app.voice.service import cancel_queued, queue_calls

log = logging.getLogger("echocare.calls")


async def call_history(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> list[CallSummary]:
    """The senior's calls, newest first, queued ones included; test calls are left out
    (04 §1, 05 §1). Out of reach is 404, as for the senior herself (AL8)."""
    await reach_senior(session, caller, senior_id)
    calls = await session.scalars(
        select(Call)
        .where(Call.senior_id == senior_id, Call.trigger != CallTrigger.test)
        .order_by(Call.created_at.desc(), Call.id.desc())
    )
    return [CallSummary.model_validate(c, from_attributes=True) for c in calls]


async def transcript(
    session: AsyncSession, caller: Caller, call_id: uuid.UUID
) -> TranscriptDetail:
    """One call with its turns, reports and answers, for the senior's registering
    medic and for DAS past `draft` (04 §1). A caregiver or the senior reaches the
    calls but not what was said, so they get 404 like a stranger."""
    call = await session.scalar(
        select(Call)
        .join(Senior, Senior.id == Call.senior_id)
        .where(
            Call.id == call_id,
            or_(reach(caller, Role.medic), reach(caller, Role.das)),
        )
    )
    if call is None:
        log.info("refused not_found: user %s, call %s", caller.user.id, call_id)
        raise refuse(404, "not_found")

    turns = [
        TurnView.model_validate(t, from_attributes=True)
        for t in await session.scalars(
            select(CallTurn)
            .where(CallTurn.call_id == call_id)
            .order_by(CallTurn.position)
        )
    ]
    reports = [
        ReportView.model_validate(r, from_attributes=True)
        for r in await session.scalars(
            select(StatusReport)
            .where(StatusReport.call_id == call_id)
            .order_by(StatusReport.at)
        )
    ]
    answers = [
        AnswerView.model_validate(a, from_attributes=True)
        for a in await session.scalars(
            select(Answer).where(Answer.call_id == call_id).order_by(Answer.at)
        )
    ]
    detail = call_detail(call, reports, turns)
    return TranscriptDetail(**detail.model_dump(), answers=answers)


async def queue_welcome_call(session: AsyncSession, senior_id: uuid.UUID) -> None:
    """The welcome call an accepted senior answers from the app's card (Q11, 04 §2).

    A senior with a live call already (`uq_calls_live_senior`, 05 §3) gets none. Doesn't
    commit: `accept` does, with the move.
    """
    await queue_calls(
        session,
        Senior.id == senior_id,
        trigger=CallTrigger.welcome,
        due_at=datetime.now(UTC),
    )


async def welcome_call_pending(session: AsyncSession, senior_id: uuid.UUID) -> bool:
    """The senior has a welcome call still to be answered: queued, ringing or in
    progress (UC-04, 04 §2)."""
    return (
        await session.scalar(
            select(
                exists().where(
                    Call.senior_id == senior_id,
                    Call.trigger == CallTrigger.welcome,
                    Call.state.in_(
                        (CallState.queued, CallState.ringing, CallState.in_progress)
                    ),
                )
            )
        )
        is True
    )


async def cancel_queued_calls(session: AsyncSession, senior_id: uuid.UUID) -> None:
    """A withdrawn senior gets no more calls (UC-04): her queued ones are canceled.

    Doesn't commit: `withdraw_consent` does, with the move.
    """
    await cancel_queued(session, Call.senior_id == senior_id, now=datetime.now(UTC))


@dataclass(frozen=True)
class AnswerContext:
    """What a picked-up call is answered with (04 §4.2)."""

    trigger: CallTrigger
    form_of_address: str
    greeting: str


async def answer_context(
    session: AsyncSession, call_id: uuid.UUID
) -> AnswerContext | None:
    """The call's trigger and its greeting, with the campaign's warning for a campaign
    call; None for an unknown call."""
    row = (
        await session.execute(
            select(Call.trigger, Senior.form_of_address, Campaign.kind, Campaign.level)
            .join(Senior, Senior.id == Call.senior_id)
            .outerjoin(Campaign, Campaign.id == Call.campaign_id)
            .where(Call.id == call_id)
        )
    ).first()
    if row is None:
        return None
    # A welcome call speaks its own script (UC-04), no greeting.
    said = (
        ""
        if row.trigger is CallTrigger.welcome
        else wellbeing_greeting(row.form_of_address, row.trigger, row.kind, row.level)
    )
    return AnswerContext(row.trigger, row.form_of_address, said)
