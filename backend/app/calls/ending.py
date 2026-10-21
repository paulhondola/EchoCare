"""The shared step that ends a call into its result (design §5, 03 §6, §8).

A call's answers, or its lack of them, become the call's final fields, a status report,
the senior's code and, on a red, an incident. The mock call calls it today. `voice` can't
import `calls` (a cycle), so the Twilio relay reaches it through `voice/router.py`, which
may import anything.

Nothing here commits: the caller owns the transaction.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.models import Campaign, CampaignKind
from app.codes.models import ReportSource, SeniorStatus
from app.codes.service import add_report, set_code
from app.core.settings import get_settings
from app.incidents.models import UNRESOLVED, Incident, IncidentStatus
from app.incidents.service import opens_incident
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Senior,
)
from app.status.engine import (
    CallAnswers,
    Question,
    Severity,
    final_severity,
    next_code,
    today_in_bucharest,
)
from app.voice.calls import CallState, advance
from app.voice.models import Call, WelcomeOutcome
from app.voice.service import queue_redial


def redial_delay() -> timedelta:
    """How long a first unanswered attempt waits for its redial (06 §3)."""
    return timedelta(seconds=20) if get_settings().demo_mode else timedelta(minutes=20)


def campaign_reason(worrying: list[Question], kind: CampaignKind) -> str:
    """What a campaign call found, in Romanian, for `reason` and the incident."""
    cold = kind is CampaignKind.cold
    if not worrying:
        shelter = "căldură" if cold else "un loc răcoros"
        return f"Se simte bine, știe ce zi este și are {shelter}"
    said = {
        Question.feeling: "se simte rău",
        Question.orientation: "nu știe ce zi este",
        Question.shelter: "nu are căldură în casă" if cold else "nu are un loc răcoros",
    }
    *init, last = [said[q] for q in Question if q in worrying]
    return (f"{', '.join(init)} și {last}" if init else last).capitalize()


async def conclude(
    session: AsyncSession, call: Call, answers: CallAnswers | None
) -> Severity | None:
    """End a call that is `in_progress` (answered) or already `unanswered`.

    Returns the result, or None when a redial was queued instead (03 §6: a campaign's
    green waits for the redial). Doesn't commit.
    """
    now = datetime.now(UTC)
    if answers is not None:
        today = today_in_bucharest()
        kind = await session.scalar(
            select(Campaign.kind).where(Campaign.id == call.campaign_id)
        )  # a call with no campaign reads as cold
        reason = campaign_reason(
            [q for q in Question if answers.worrying(q, today)],
            kind or CampaignKind.cold,
        )
        certainty = answers.certainty()
        result = final_severity(
            starting=call.starting_severity,
            answered=True,
            rules=answers.severity(today),
            certainty=certainty,
        )
        call.state = advance(call.state, CallState.completed)
        call.ended_at = now
        call.final_certainty = certainty
        call.summary = f"Apel simulat din aplicație. {reason}."
        source = ReportSource.rules
    elif call.attempt == 1:
        await add_report(
            session,
            call.id,
            ReportSource.unanswered,
            call.starting_severity,
            "Nu a răspuns la prima încercare",
        )
        await queue_redial(session, call, now + redial_delay())
        return None
    else:
        reason = "Nu a răspuns de două ori"
        certainty = None  # certainty exists only for an answered call (D7)
        result = final_severity(starting=call.starting_severity, answered=False)
        source = ReportSource.unanswered
    call.final_severity = result
    call.reason = reason
    await add_report(session, call.id, source, result, reason, certainty=certainty)

    current = await session.scalar(
        select(SeniorStatus.code).where(SeniorStatus.senior_id == call.senior_id)
    )
    unresolved = await session.scalar(
        select(
            exists().where(
                Incident.senior_id == call.senior_id,
                Incident.status.in_(UNRESOLVED),
            )
        )
    )
    # A red whose incident is unresolved stays as it is (03 §8, P9).
    if next_code(current, unresolved, result) is result:
        await set_code(session, call.senior_id, call.id, result, reason, now)
    if opens_incident(result, unresolved):
        session.add(
            Incident(
                senior_id=call.senior_id,
                status=IncidentStatus.open,
                opened_by_call_id=call.id,
                reason=reason,
            )
        )
    return result


async def conclude_welcome(
    session: AsyncSession,
    call: Call,
    *,
    given: bool,
    method: ConsentMethod,
    text_version: str,
) -> bool:
    """End an `in_progress` welcome call with the senior's answer to the consent text.

    False, with nothing written, when the senior is no longer `accepted`: of two moves
    at once one wins (05 §3's pattern). Doesn't commit.
    """
    now = datetime.now(UTC)
    moved = await session.scalar(
        update(Senior)
        .where(
            Senior.id == call.senior_id,
            Senior.enrollment_state == EnrollmentState.accepted,
        )
        .values(
            enrollment_state=EnrollmentState.active
            if given
            else EnrollmentState.refused
        )
        .returning(Senior.id)
    )
    if moved is None:
        return False
    call.welcome_outcome = WelcomeOutcome.confirmed
    call.state = advance(call.state, CallState.completed)
    call.ended_at = now
    session.add(
        Consent(
            senior_id=call.senior_id,
            decision=ConsentDecision.given if given else ConsentDecision.refused,
            method=method,
            text_version=text_version,
            call_id=call.id,
        )
    )
    if given:
        # The code starts when consent is given (03 §8).
        await set_code(
            session, call.senior_id, call.id, Severity.green, "Consimțământ dat", now
        )
    return True
