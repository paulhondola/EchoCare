"""The shared step that ends a call into its result (design §5, 03 §6, §8).

A call's answers, or its lack of them, become the call's final fields, a status report,
the senior's code and, on a red, an incident. The mock call calls it today. `voice` can't
import `calls` (a cycle), so the Twilio relay reaches it through `voice/router.py`, which
may import anything.

Nothing here commits but `settle`: the caller owns the transaction.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaigns.models import Campaign, CampaignKind
from app.codes.models import ReportSource, SeniorStatus, StatusReport
from app.codes.service import add_report, set_code
from app.core.db import Session
from app.core.settings import get_settings
from app.incidents.models import UNRESOLVED, Incident
from app.incidents.service import note_red_added, open_incident, opens_incident
from app.seniors.models import ConsentMethod, EnrollmentState
from app.seniors.service import confirm_welcome, end_welcome
from app.status.engine import (
    Answer,
    CallAnswers,
    Certainty,
    Question,
    Severity,
    final_severity,
    next_code,
    today_in_bucharest,
)
from app.voice.calls import CallState
from app.voice.models import Answer as StoredAnswer
from app.voice.models import Call, CallTrigger, WelcomeOutcome
from app.voice.service import (
    finish,
    live_call_for_update,
    queue_redial,
    transition,
)

INCOMPLETE_REASON = "Nu a răspuns la toate întrebările"
# The code's reason when a watch or „Sunați-mă” call is not answered the first time (03 §6)
NOT_REACHED = {
    CallTrigger.watch: "Nu a răspuns după semnalul ceasului",
    CallTrigger.manual: "Nu a răspuns după cererea de apel",
}
LINE_LOST_SUMMARY = "Convorbirea s-a întrerupt."
# Sources that hand a call over red; any other hand-over is yellow (03 §6, 04 §4.4).
RED_SOURCES = frozenset(
    {
        ReportSource.alarm_tier1,
        ReportSource.alarm_tier2,
        ReportSource.raise_concern,
        ReportSource.rules,
    }
)


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


async def stored_answers(session: AsyncSession, call_id: uuid.UUID) -> CallAnswers:
    """The call's stored answers in the order heard, the overwrite rule applied (03 §3)."""
    answers = CallAnswers()
    rows = await session.scalars(
        select(StoredAnswer)
        .where(StoredAnswer.call_id == call_id)
        .order_by(StoredAnswer.at)
    )
    for row in rows:
        answers.record(row.field, Answer(row.value, row.clear, row.quote))
    return answers


async def stored_concern(session: AsyncSession, call_id: uuid.UUID) -> Severity | None:
    """The highest severity the call raised as a concern, if any (03 §6)."""
    found = await session.scalars(
        select(StatusReport.severity).where(
            StatusReport.call_id == call_id,
            StatusReport.source == ReportSource.raise_concern,
        )
    )
    return max(found, default=None)


async def save_concern(call_id: uuid.UUID, severity: Severity, reason: str) -> None:
    """A concern the agent raised, committed as it comes (03 §6). Owns its session."""
    async with Session() as session:
        add_report(session, call_id, ReportSource.raise_concern, severity, reason[:200])
        await session.commit()


async def call_reason(session: AsyncSession, call: Call, answers: CallAnswers) -> str:
    """What the answers found, in Romanian; INCOMPLETE_REASON when nothing worrying was
    said and a question is missing or unclear (unclear never counts as fine, 03 §5)."""
    kind = await session.scalar(
        select(Campaign.kind).where(Campaign.id == call.campaign_id)
    )  # a call with no campaign reads as cold
    today = today_in_bucharest()
    worrying = [q for q in Question if answers.worrying(q, today)]
    if not worrying and answers.unclear():
        return INCOMPLETE_REASON
    return campaign_reason(worrying, kind or CampaignKind.cold)


async def code_now(
    session: AsyncSession, senior_id: uuid.UUID
) -> tuple[Severity | None, bool]:
    """The senior's current code, and whether an incident of hers is unresolved."""
    current = await session.scalar(
        select(SeniorStatus.code).where(SeniorStatus.senior_id == senior_id)
    )
    unresolved = await session.scalar(
        select(
            exists().where(
                Incident.senior_id == senior_id, Incident.status.in_(UNRESOLVED)
            )
        )
    )
    return current, bool(unresolved)


async def conclude(
    session: AsyncSession,
    call: Call,
    answers: CallAnswers | None,
    *,
    summary: str = "Apel simulat din aplicație.",
    concern: Severity | None = None,
    dropped: bool = False,
) -> Severity | None:
    """End a call that is `in_progress` (answered) or already `unanswered`.

    Returns the result, or None when a redial was queued instead (03 §6: a campaign's
    green waits for the redial). A dropped call counts as answered with low certainty
    and is never redialed (03 §9). Doesn't commit.
    """
    now = datetime.now(UTC)
    if answers is not None:
        reason = await call_reason(session, call, answers)
        certainty = Certainty.low if dropped else answers.certainty()
        result = final_severity(
            starting=call.starting_severity,
            answered=True,
            rules=answers.severity(today_in_bucharest()),
            certainty=certainty,
            concern=concern,
        )
        end = CallState.dropped if dropped else CallState.completed
        summary = f"{summary} {reason}."
        source = ReportSource.rules
    elif call.attempt == 1:
        add_report(
            session,
            call.id,
            ReportSource.unanswered,
            call.starting_severity,
            "Nu a răspuns la prima încercare",
        )
        # A trigger's yellow acts on the first unanswered attempt; a campaign's green
        # waits for the redial (03 §6)
        if call.trigger in NOT_REACHED:
            current, unresolved = await code_now(session, call.senior_id)
            if next_code(current, unresolved, call.starting_severity) is (
                call.starting_severity
            ):
                await set_code(
                    session,
                    call.senior_id,
                    call.id,
                    call.starting_severity,
                    NOT_REACHED[call.trigger],
                    now,
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

    current, unresolved = await code_now(session, call.senior_id)
    # A red whose incident is unresolved stays as it is (03 §8, P9).
    if next_code(current, unresolved, result) is result:
        await set_code(session, call.senior_id, call.id, result, reason, now)
    if opens_incident(result, unresolved):
        open_incident(session, call.senior_id, call.id, reason)
    else:
        await note_red_added(session, call.senior_id, result, current)
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
    failed then runs the redial-or-yellow rule (06 §1). A welcome call that ends with
    nobody through the script, a hang-up included, runs the welcome retry rule (UC-04).
    Test calls run neither (05 §1). Commits; returns the state it moved to, or None.
    """
    moved = await transition(session, call_id, sid, new, only_from=only_from)
    if moved in (CallState.unanswered, CallState.failed, CallState.dropped):
        call = await session.get(Call, call_id)  # the row transition just locked
        if call.trigger is CallTrigger.welcome:
            # Already ended in `moved`: `finish` only adds the outcome.
            now = datetime.now(UTC)
            finish(call, moved, now, welcome_outcome=WelcomeOutcome.no_answer)
            await retry_welcome(session, call)
        elif call.trigger is not CallTrigger.test:
            if moved is CallState.dropped:
                # Concluded from what was stored; no redial (03 §9).
                await conclude(
                    session,
                    call,
                    await stored_answers(session, call_id),
                    summary=LINE_LOST_SUMMARY,
                    concern=await stored_concern(session, call_id),
                    dropped=True,
                )
            else:
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
    evidence: dict[str, Any] | None = None,
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
        evidence=evidence,
    ):
        return False
    finish(call, CallState.completed, now, welcome_outcome=WelcomeOutcome.confirmed)
    if given:
        # The code starts when consent is given (03 §8).
        await set_code(
            session, call.senior_id, call.id, Severity.green, "Consimțământ dat", now
        )
    return True


async def retry_welcome(session: AsyncSession, call: Call) -> None:
    """A welcome call that ended without an answer to the consent text: the first one
    is tried again after the redial delay, a second makes the senior `unreachable`
    (UC-04). `call` has ended already, so the retry never meets a live call for the
    senior (05 §3). Doesn't commit.
    """
    if call.attempt == 1:
        queue_redial(session, call, datetime.now(UTC) + redial_delay())
    else:
        await end_welcome(session, call.senior_id, EnrollmentState.unreachable)


async def close_welcome(
    session: AsyncSession, call: Call, outcome: WelcomeOutcome
) -> bool:
    """End an `in_progress` welcome call that did not reach consent: a wrong number, or
    one the retry rule takes (UC-04). It is marked completed before the goodbye, so
    Twilio's later `completed` leaves it so (03 §9).

    False, with nothing written, for a call no longer in progress: a repeated callback
    ends nothing twice. Doesn't commit.
    """
    if call.state is not CallState.in_progress:
        return False
    finish(call, CallState.completed, datetime.now(UTC), welcome_outcome=outcome)
    if outcome is WelcomeOutcome.wrong_number:
        await end_welcome(session, call.senior_id, EnrollmentState.wrong_number)
    else:
        await session.flush()  # the call leaves the live index before its retry
        await retry_welcome(session, call)
    return True


async def end_wellbeing(
    call_id: uuid.UUID, summary: str, *, dropped: bool = False
) -> Severity | None:
    """The agent ends a wellbeing call from what was stored. Owns its session, like
    `begin_handover`. None, with nothing written, once the call is no longer in progress."""
    async with Session() as session:
        call = await live_call_for_update(session, call_id)
        if call is None:
            return None
        result = await conclude(
            session,
            call,
            await stored_answers(session, call_id),
            summary=summary,
            concern=await stored_concern(session, call_id),
            dropped=dropped,
        )
        await session.commit()
    return result


async def begin_handover(
    call_id: uuid.UUID, source: ReportSource, reason: str | None
) -> bool:
    """A call going to a person (04 §4.4): key 9 (`request_human`, at least yellow) or
    a tier 1 phrase (`alarm_tier1`, red), or the agent's own (red per `RED_SOURCES`;
    `reason=None` is what the stored answers found). Every hand-over opens an incident, or joins
    the senior's unresolved one, so the DAS phone that rings shows who is calling
    (design §4). Written before the session closes, so a line lost now keeps it.

    Owns its session, like `voice.service.save_turn`: the relay holds none (ADR-004).
    False, with nothing written, once the call is no longer in progress.
    """
    severity = Severity.red if source in RED_SOURCES else Severity.yellow
    async with Session() as session:
        call = await live_call_for_update(session, call_id)
        if call is None:
            return False
        now = datetime.now(UTC)
        answers = await stored_answers(session, call_id)
        # A red already heard stays red, whatever started the hand-over (03 §6).
        severity = max(
            severity,
            answers.severity(today_in_bucharest()),
            await stored_concern(session, call_id) or Severity.green,
        )
        if reason is None:
            reason = await call_reason(session, call, answers)
        reason = reason[:200]  # String(200) in reports and the code (05 §2)
        add_report(session, call.id, source, severity, reason)
        current = await session.scalar(
            select(SeniorStatus.code).where(SeniorStatus.senior_id == call.senior_id)
        )
        # Never lowers the code; a red kept by its incident stays as it is (03 §8).
        if current is None or severity >= current:
            await set_code(session, call.senior_id, call.id, severity, reason, now)
        unresolved = await session.scalar(
            select(
                exists().where(
                    Incident.senior_id == call.senior_id,
                    Incident.status.in_(UNRESOLVED),
                )
            )
        )
        if not unresolved:
            open_incident(session, call.senior_id, call.id, reason)
        else:
            await note_red_added(session, call.senior_id, severity, current)
        finish(call, CallState.handed_over, now, final_severity=severity, reason=reason)
        await session.commit()
    return True
