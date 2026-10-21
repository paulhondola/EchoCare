"""The mock campaign call: the senior's app answers a queued call in place of a phone
line (design §4.2, §5, Q8, Q14).

The walk through the call's states and the transcript are written here; the result of
the answers is `ending.conclude`, the step a real call shares. Never in production
(Q10), where the line is real.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse
from app.calls.ending import conclude, conclude_welcome
from app.calls.schemas import MockAnswerForm, MockCallView
from app.campaigns.models import Campaign, CampaignKind, WarningLevel
from app.campaigns.service import cancel_lapsed
from app.core.settings import AppEnv, get_settings
from app.seniors.models import ConsentMethod, EnrollmentState, Senior
from app.seniors.service import reach
from app.status.engine import Answer as RuleAnswer
from app.status.engine import CallAnswers, Question, Severity
from app.voice.calls import CallState, advance
from app.voice.dialogue import CARD_CONSENT_TEXT, CARD_CONSENT_VERSION
from app.voice.models import Answer, Call, CallTrigger, CallTurn, Speaker, TurnKind

log = logging.getLogger("echocare.calls")

# The state a senior must be in for a call of each trigger to be offered (design §4.2).
REQUIRES = {
    CallTrigger.campaign: EnrollmentState.active,
    CallTrigger.welcome: EnrollmentState.accepted,
}

SIMULATED = "Apel simulat din aplicație, fără linie telefonică."
DECLINED = "Seniorul a ales „Nu acum”."
WELCOME_GOODBYE = {
    True: "Vă mulțumim. Nu vă vom cere niciodată bani sau date. O zi bună!",
    False: "Am înțeles. Nu vă vom mai suna. O zi bună!",
}


def forbid_in_production(caller: Caller) -> None:
    """The mock stands in for a phone line, which production has (Q10)."""
    if get_settings().app_env is AppEnv.production:
        # debug: release apps poll the card every 30 s
        log.debug("refused not_found: mock call in production, user %s", caller.user.id)
        raise refuse(404, "not_found")


async def due_mock_call(session: AsyncSession, caller: Caller) -> MockCallView | None:
    """The senior's oldest queued call that is due and whose senior is in the state its
    trigger needs, or None. Commits, since it cancels lapsed campaigns' calls first."""
    forbid_in_production(caller)
    if Role.senior not in caller.roles:
        log.info("refused not_allowed: user %s", caller.user.id)
        raise refuse(403, "not_allowed")
    await cancel_lapsed(session)
    row = (
        await session.execute(
            select(Call.id, Call.trigger, Campaign.kind, Campaign.level)
            .join(Senior, Senior.id == Call.senior_id)
            .outerjoin(Campaign, Campaign.id == Call.campaign_id)
            .where(
                reach(caller, Role.senior),
                Call.state == CallState.queued,
                Call.due_at <= datetime.now(UTC),
                or_(
                    *(
                        and_(Call.trigger == trigger, Senior.enrollment_state == state)
                        for trigger, state in REQUIRES.items()
                    )
                ),
            )
            .order_by(Call.due_at, Call.created_at, Call.id)
            .limit(1)
        )
    ).first()
    await session.commit()
    if row is None:
        return None
    call_id, trigger, kind, level = row
    welcome = trigger is CallTrigger.welcome
    return MockCallView(
        call_id=call_id,
        trigger=trigger,
        campaign_kind=kind,
        campaign_level=level,
        consent_text=CARD_CONSENT_TEXT if welcome else None,
        text_version=CARD_CONSENT_VERSION if welcome else None,
    )


async def answer_mock_call(
    session: AsyncSession, caller: Caller, call_id: uuid.UUID, form: MockAnswerForm
) -> None:
    """Walk the call through the states a real one passes, write its transcript and end
    it through `conclude`, or `conclude_welcome` for a welcome call. Commits.

    Refused, in this order: not the caller's senior's call 404, already ended 409
    `already_done`, no longer answerable 409 `wrong_state`, a body that doesn't fit the
    trigger 422 `incomplete`. Nothing changes on a refusal.
    """
    forbid_in_production(caller)
    await cancel_lapsed(session)
    row = (
        await session.execute(
            select(
                Call,
                Senior.enrollment_state,
                Senior.form_of_address,
                Campaign.kind,
                Campaign.level,
            )
            .join(Senior, Senior.id == Call.senior_id)
            .outerjoin(Campaign, Campaign.id == Call.campaign_id)
            .where(Call.id == call_id, reach(caller, Role.senior))
            .with_for_update(of=Call)  # of two taps at once, the second sees the first
        )
    ).one_or_none()
    if row is None:
        log.info("refused not_found: user %s, call %s", caller.user.id, call_id)
        raise refuse(404, "not_found")
    call, enrollment, address, kind, level = row

    if call.state in (CallState.completed, CallState.unanswered):
        log.info("refused already_done: user %s, call %s", caller.user.id, call_id)
        raise refuse(409, "already_done")
    now = datetime.now(UTC)
    # A trigger with no entry (watch, manual, test) is never answered here: the senior's
    # state is never None.
    if (
        call.state is not CallState.queued
        or call.due_at > now
        or enrollment is not REQUIRES.get(call.trigger)
    ):
        log.info("refused wrong_state: user %s, call %s", caller.user.id, call_id)
        raise refuse(409, "wrong_state")
    if call.trigger is CallTrigger.welcome:
        await answer_welcome(session, caller, call, form)
        return

    given = {"feeling": form.feeling, "day": form.day, "shelter": form.shelter}
    missing = [name for name, value in given.items() if value is None]
    if missing and not form.declined:
        log.info("refused incomplete: user %s, call %s", caller.user.id, call_id)
        raise refuse(422, "incomplete", missing=missing)

    lines = [(Speaker.system, SIMULATED)]
    call.state = advance(call.state, CallState.ringing)
    if form.declined:
        call.state = advance(call.state, CallState.unanswered)
        call.ended_at = now
        await conclude(session, call, None)
        lines.append((Speaker.system, DECLINED))
    else:
        call.state = advance(call.state, CallState.in_progress)
        call.started_at = now
        values = {
            Question.feeling: form.feeling,
            Question.orientation: form.day,
            Question.shelter: form.shelter,
        }
        said = {
            Question.feeling: "Bine" if form.feeling == "ok" else "Rău",
            Question.orientation: (
                "Nu știu" if form.day == "unknown" else form.day.capitalize()
            ),
            Question.shelter: "Da" if form.shelter == "yes" else "Nu",
        }
        result = await conclude(
            session,
            call,
            CallAnswers({q: RuleAnswer(values[q], True, said[q]) for q in Question}),
        )
        lines += [
            (Speaker.agent, greeting(address, kind, level)),
            (Speaker.senior, said[Question.feeling]),
            (Speaker.agent, "Ce zi este azi?"),
            (Speaker.senior, said[Question.orientation]),
            (
                Speaker.agent,
                "Aveți un loc răcoros?"
                if kind is CampaignKind.heat
                else "Aveți căldură în casă?",
            ),
            (Speaker.senior, said[Question.shelter]),
            (
                Speaker.agent,
                f"{address[:1].upper()}{address[1:]}, un dispecer DAS a fost anunțat."
                if result is Severity.red
                else f"Vă mulțumesc, {address}. O zi bună!",
            ),
        ]
        # One microsecond apart: the transcript lists answers by `at`, in question order.
        session.add_all(
            Answer(
                call_id=call.id,
                field=q,
                value=values[q],
                clear=True,
                quote=said[q],
                at=now + timedelta(microseconds=i),
            )
            for i, q in enumerate(Question)
        )
    session.add_all(turns(call, lines))
    await session.commit()


def turns(call: Call, lines: list[tuple[Speaker, str]]) -> list[CallTurn]:
    """The transcript rows for `lines`, numbered from 1."""
    return [
        CallTurn(
            call_id=call.id,
            position=position,
            speaker=speaker,
            kind=TurnKind.speech,
            content=content,
        )
        for position, (speaker, content) in enumerate(lines, start=1)
    ]


async def answer_welcome(
    session: AsyncSession, caller: Caller, call: Call, form: MockAnswerForm
) -> None:
    """The card's „Da” or „Nu” ends the welcome call through `conclude_welcome` (Q11).

    422 `incomplete` without a `consent`; 409 `wrong_state` when the senior left
    `accepted` since the check, with nothing written. Commits.
    """
    if form.consent is None:
        log.info("refused incomplete: user %s, call %s", caller.user.id, call.id)
        raise refuse(422, "incomplete", missing=["consent"])
    call.state = advance(call.state, CallState.ringing)
    call.state = advance(call.state, CallState.in_progress)
    call.started_at = datetime.now(UTC)
    if not await conclude_welcome(
        session,
        call,
        given=form.consent,
        method=ConsentMethod.app,
        text_version=CARD_CONSENT_VERSION,
    ):
        log.info("refused wrong_state: user %s, call %s", caller.user.id, call.id)
        raise refuse(409, "wrong_state")
    session.add_all(
        turns(
            call,
            [
                (Speaker.system, SIMULATED),
                (Speaker.agent, CARD_CONSENT_TEXT),
                (Speaker.senior, "Da" if form.consent else "Nu"),
                (Speaker.agent, WELCOME_GOODBYE[form.consent]),
            ],
        )
    )
    await session.commit()


def greeting(
    address: str, kind: CampaignKind | None, level: WarningLevel | None
) -> str:
    """The agent's opening, naming the warning (04 §4's greeting, the seed's wording)."""
    code = "roșu" if level is WarningLevel.red else "galben"
    weather = "caniculă" if kind is CampaignKind.heat else "ger"
    return (
        f"Bună ziua, {address}. Sunt asistentul automat al DAS Timișoara. "
        f"Vă sunăm pentru că azi e cod {code} de {weather}. Cum vă simțiți?"
    )
