"""The shared step that ends a call into its result (design §5, 03 §6, §8).

A call's answers, or its lack of them, become the call's final fields, a status report,
the senior's code and, on a red, an incident. The mock call calls it today. `voice` can't
import `calls` (a cycle), so the Twilio relay reaches it through `voice/router.py`, which
may import anything.

Nothing here commits but `settle`: the caller owns the transaction.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.models import Campaign, CampaignKind
from app.codes.models import ReportSource, SeniorStatus
from app.codes.service import add_report, set_code
from app.core.settings import get_settings
from app.incidents.models import UNRESOLVED, Incident
from app.incidents.service import open_incident, opens_incident
from app.seniors.models import (
    ConsentMethod,
)
from app.seniors.service import confirm_welcome
from app.status.engine import (
    CallAnswers,
    Question,
    Severity,
    final_severity,
    next_code,
    today_in_bucharest,
)
from app.voice.calls import CallState
from app.voice.models import Call, CallTrigger, WelcomeOutcome
from app.voice.service import finish, queue_redial, transition


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
        end, summary = CallState.completed, f"Apel simulat din aplicație. {reason}."
        source = ReportSource.rules
    elif call.attempt == 1:
        add_report(
            session,
            call.id,
            ReportSource.unanswered,
            call.starting_severity,
            "Nu a răspuns la prima încercare",
        )
        queue_redial(session, call, now + redial_delay())
        return None
    else:
        reason = "Nu a răspuns de două ori"
        certainty = None  # certainty exists only for an answered call (D7)
        result = final_severity(starting=call.starting_severity, answered=False)
        source = ReportSource.unanswered
        end, summary = call.state, None  # already unanswered: ended_at stays
    finish(
        call,
        end,
        now,
        final_severity=result,
        final_certainty=certainty,
        reason=reason,
        summary=summary,
    )
    add_report(session, call.id, source, result, reason, certainty=certainty)

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
        open_incident(session, call.senior_id, call.id, reason)
    return result


async def settle(
    session: AsyncSession,
    call_id: uuid.UUID,
    sid: str | None,
    new: CallState | None,
    *,
    only_from: CallState | None = None,
) -> CallState | None:
    """Apply Twilio's word on a call (`transition`); a real call that ends unanswered or
    failed then runs the redial-or-yellow rule (06 §1). Welcome and test calls don't:
    no campaign waits on them. Commits; returns the state it moved to, or None.
    """
    moved = await transition(session, call_id, sid, new, only_from=only_from)
    if moved in (CallState.unanswered, CallState.failed):
        call = await session.get(Call, call_id)  # the row transition just locked
        if call.trigger not in (CallTrigger.welcome, CallTrigger.test):
            await conclude(session, call, None)
    await session.commit()
    return moved


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
    if not await confirm_welcome(
        session,
        call.senior_id,
        call.id,
        given=given,
        method=method,
        text_version=text_version,
    ):
        return False
    finish(call, CallState.completed, now, welcome_outcome=WelcomeOutcome.confirmed)
    if given:
        # The code starts when consent is given (03 §8).
        await set_code(
            session, call.senior_id, call.id, Severity.green, "Consimțământ dat", now
        )
    return True
