import json
import logging
import uuid
from collections.abc import Callable
from functools import cache, partial
from typing import Annotated
from urllib.parse import parse_qsl
from xml.sax.saxutils import quoteattr

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import Agent, Line, Send
from app.agent.model import ModelStream, stream_with
from app.agent.relay import Escalation, HandOver, Relay
from app.agent.session import Echo, Handler, serve
from app.auth.service import on_duty, refuse
from app.calls.ending import (
    begin_handover,
    close_welcome,
    conclude_welcome,
    end_wellbeing,
    save_concern,
    settle,
)
from app.calls.service import AnswerContext, answer_context
from app.codes.models import ReportSource
from app.core.db import Session, get_session
from app.core.llm import deepinfra_model
from app.core.phones import mask
from app.core.settings import get_settings
from app.incidents.service import take_for_handover
from app.seniors.models import ConsentMethod
from app.voice.calls import (
    TWILIO_DIALING,
    TWILIO_STATUSES,
    CallState,
    answered_by_machine,
)
from app.voice.dialogue import (
    CALL_BACK,
    CONSENT_TEXT,
    CONSENT_VERSION,
    LANGUAGE,
    SORRY,
    STOP_TRANSCRIPTION,
    TRANSCRIPTION_FAILED,
    dial_on_duty,
    gather,
    hangup,
    say,
    say_and_hang_up,
    sorry,
    transcribed,
    twiml,
)
from app.voice.models import CallTrigger, Speaker, TurnKind, WelcomeOutcome
from app.voice.service import (
    answer_handover,
    append_turn,
    form_of_address,
    live_call_for_update,
    move_call,
    save_answer,
    save_turn,
    transition,
)
from app.voice.twilio import (
    dial_allowed,
    handover_ring_seconds,
    hang_up,
    public_url,
    signed,
    voice_url,
)
from app.voice.welcome import (
    GIVEN,
    NOT_AVAILABLE,
    NOT_HEARD,
    REFUSED,
    SILENT,
    UNCLEAR,
    WRONG_NUMBER,
    consent_answer,
    evidence,
    heard,
    identity,
    identity_answer,
)

log = logging.getLogger("echocare.voice")

router = APIRouter()


async def twilio_params(request: Request) -> dict[str, str]:
    """The callback's form parameters, if Twilio signed them; otherwise 403."""
    params = parse_qsl((await request.body()).decode(), keep_blank_values=True)
    url = public_url(request.url.path, request.url.query)
    if not signed(request.headers.get("x-twilio-signature", ""), [url], params):
        log.warning("refused not_allowed: unsigned callback to %s", request.url.path)
        raise refuse(403, "not_allowed")
    return dict(params)


Params = Annotated[dict[str, str], Depends(twilio_params)]
Db = Annotated[AsyncSession, Depends(get_session)]


async def agent_turn(session: AsyncSession, call: uuid.UUID, text: str) -> None:
    """What the call says next, as the agent's transcript turn (05 §1). Doesn't
    commit."""
    await append_turn(session, call, Speaker.agent, TurnKind.speech, text)


async def exchange(
    session: AsyncSession, call: uuid.UUID, params: dict[str, str], text: str
) -> None:
    """The senior's `<Gather>` answer, if any, then what the call says next, as
    transcript turns (05 §1). Doesn't commit."""
    if answer := heard(params):
        kind, content, confidence = answer
        await append_turn(
            session, call, Speaker.senior, kind, content, confidence=confidence
        )
    await agent_turn(session, call, text)


def hung_up(params: dict[str, str]) -> bool:
    """The senior's leg has ended: Twilio still calls a `<Connect>` or `<Dial>` action,
    but nobody hears what it answers, so nothing is stored as said."""
    return params.get("CallStatus") == "completed"


async def call_back(
    session: AsyncSession, call: uuid.UUID, params: dict[str, str]
) -> Response:
    """„Someone will call you back”, then hang up; the sentence is stored as the
    agent's unless the senior has hung up, and still said if the database cannot take
    it (UC-07)."""
    if not hung_up(params):
        try:
            await agent_turn(session, call, CALL_BACK)
            await session.commit()
        except SQLAlchemyError, OSError:
            log.exception("hand-over for call %s: database unavailable", call)
    return say_and_hang_up(CALL_BACK)


@router.post("/voice/answer")
async def answer(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Picked up: a welcome call gets its script; any other connects to
    ConversationRelay in ro-RO, whose end comes back to the hand-over address
    (04 §4.2)."""
    try:
        context = await answer_context(session, call)
    except SQLAlchemyError, OSError:
        log.exception("answer for call %s: database unavailable", call)
        return sorry()
    if context is None:
        log.warning("answer for unknown call %s", call)
        return sorry()
    if context.trigger is CallTrigger.welcome:
        return await welcome(call, params, session)
    s = get_settings()
    attrs = {
        "url": voice_url("relay", call, scheme="wss"),
        "language": LANGUAGE,
        "ttsProvider": s.twilio_tts_provider,
        "voice": s.twilio_voice,
        "welcomeGreeting": context.greeting,
        "dtmfDetection": "true",
        # A senior who answers over the greeting, or presses 9 during it, must be heard:
        # Twilio's default since May 2025, `none`, drops both (04 §4.3).
        "reportInputDuringAgentSpeech": "any",
        # On a speakerphone the agent hears itself; this drops its own words.
        "echoPromptFiltering": "true",
        # A turn ends 2 s after the senior stops, not when the provider decides: on a
        # noisy line `auto` sent nothing until the hang-up.
        "speechTimeout": "2000",
        # When each side speaks and what was played, for the session's log.
        "events": "speaker-events tokens-played",
    }
    relay_tag = "".join(f" {name}={quoteattr(value)}" for name, value in attrs.items())
    action = quoteattr(voice_url("handoff", call))
    return twiml(f"<Connect action={action}><ConversationRelay{relay_tag}/></Connect>")


@router.post("/voice/welcome")
async def welcome(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Picked up: the welcome call asks who answers (04 §4.2, UC-04 step 2)."""
    try:
        addressed = await form_of_address(session, call)
        if addressed is None:
            log.warning("welcome for unknown call %s", call)
            return sorry()
        await move_call(session, call, params.get("CallSid"), CallState.in_progress)
        question = identity(addressed)
        await agent_turn(session, call, question)
        await session.commit()
    except SQLAlchemyError, OSError:
        log.exception("welcome for call %s: database unavailable", call)
        return sorry()
    return gather(voice_url("welcome/identity", call, ask="1"), question)


Ask = Annotated[int, Query(alias="ask", ge=1, le=2)]
IDENTITY_ENDINGS = {
    WelcomeOutcome.not_available: NOT_AVAILABLE,
    WelcomeOutcome.wrong_number: WRONG_NUMBER,
}


@router.post("/voice/welcome/identity")
async def welcome_identity(
    call: uuid.UUID, ask: Ask, params: Params, session: Db
) -> Response:
    """Who answered (UC-04 step 2): the senior goes on to consent; „not now” and a
    wrong number end the call; silence asks once more."""
    try:
        row = await live_call_for_update(session, call)
        if row is None:
            log.warning("welcome identity for a call not in progress: %s", call)
            return sorry()
        outcome = identity_answer(
            params.get("Digits", ""), params.get("SpeechResult", "")
        )
        if outcome is WelcomeOutcome.confirmed:
            await exchange(session, call, params, CONSENT_TEXT)
            await session.commit()
            return gather(voice_url("welcome/consent", call, ask="1"), CONSENT_TEXT)
        if outcome is None and ask == 1:
            again = f"{NOT_HEARD} {identity(await form_of_address(session, call))}"
            await exchange(session, call, params, again)
            await session.commit()
            return gather(voice_url("welcome/identity", call, ask="2"), again)
        goodbye = IDENTITY_ENDINGS.get(outcome, SILENT)
        await close_welcome(session, row, outcome or WelcomeOutcome.no_answer)
        await exchange(session, call, params, goodbye)
        await session.commit()
    except SQLAlchemyError, OSError:
        log.exception("welcome identity for call %s: database unavailable", call)
        return sorry()
    return say_and_hang_up(goodbye)


@router.post("/voice/welcome/consent")
async def welcome_consent(
    call: uuid.UUID, ask: Ask, params: Params, session: Db
) -> Response:
    """The consent text's answer (UC-04 step 3): recorded on key 1 or 2, or an exact
    „da” or „nu” (G7); key 0 reads it again; anything else is asked once more."""
    digits = params.get("Digits", "")
    try:
        row = await live_call_for_update(session, call)
        if row is None:
            log.warning("welcome consent for a call not in progress: %s", call)
            return sorry()
        if digits == "0":
            await exchange(session, call, params, CONSENT_TEXT)
            await session.commit()
            return gather(
                voice_url("welcome/consent", call, ask=str(ask)), CONSENT_TEXT
            )
        given = consent_answer(digits, params.get("SpeechResult", ""))
        if given is None and ask == 1:
            await exchange(session, call, params, CONSENT_TEXT)
            await session.commit()
            return gather(voice_url("welcome/consent", call, ask="2"), CONSENT_TEXT)
        if given is None:
            await close_welcome(session, row, WelcomeOutcome.confirmed)
            said = UNCLEAR
        elif await conclude_welcome(
            session,
            row,
            given=given,
            method=ConsentMethod.call,
            text_version=CONSENT_VERSION,
            evidence=evidence(params),
        ):
            said = GIVEN if given else REFUSED
        else:
            # No longer `accepted` (withdrawn meanwhile): end the call, record nothing.
            await transition(session, call, None, CallState.completed)
            said = SORRY
        await exchange(session, call, params, said)
        await session.commit()
    except SQLAlchemyError, OSError:
        log.exception("welcome consent for call %s: database unavailable", call)
        return sorry()
    return say_and_hang_up(said)


@router.post("/voice/status", status_code=204)
async def status(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Rings, answered, completed, not answered, busy, failed (04 §4.2)."""
    twilio_status = params.get("CallStatus", "")
    log.info("call %s: Twilio status %s", call, twilio_status)
    new = TWILIO_STATUSES.get(twilio_status)
    if new is None and twilio_status not in TWILIO_DIALING:
        log.warning("call %s: unknown Twilio status %r", call, twilio_status)
    await settle(session, call, params.get("CallSid"), new)
    return Response(status_code=204)


@router.post("/voice/amd", status_code=204)
async def amd(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Voicemail detection: a machine is ended and counted as unanswered (04 §4.2)."""
    answered_by = params.get("AnsweredBy", "")
    log.info("call %s: answered by %s", call, answered_by)
    if answered_by_machine(answered_by):
        sid = params.get("CallSid")
        moved = await settle(session, call, sid, CallState.unanswered)
        if moved is CallState.unanswered and sid:
            try:
                await hang_up(sid)
            except httpx.HTTPError:
                log.warning(
                    "call %s: could not hang up on the machine", call, exc_info=True
                )
    return Response(status_code=204)


@router.post("/voice/handoff")
async def handoff(call: uuid.UUID, params: Params, session: Db) -> Response:
    """The relay session ended, the `<Connect>` action (04 §4.4 step 3). With hand-over
    data, ring the on-duty phone; nobody on duty, or a number we may not ring, hears
    that someone will call back. Without, the session ended normally: hang up."""
    try:
        data = json.loads(params.get("HandoffData", ""))
    except ValueError:
        data = None
    if not isinstance(data, dict) or data.get("call") != str(call):
        return hangup()
    try:
        duty = await on_duty(session)
    except SQLAlchemyError, OSError:
        log.exception("hand-over for call %s: database unavailable", call)
        return say_and_hang_up(CALL_BACK)
    if duty is None:
        log.warning("hand-over for call %s: nobody on duty", call)
        return await call_back(session, call, params)
    user, phone = duty
    # The allowlist guards every number we ring, staff included (design §5).
    if not dial_allowed(phone):
        log.warning(
            "refused hand-over for call %s: %s is not on DIAL_ALLOWLIST",
            call,
            mask(phone),
        )
        return await call_back(session, call, params)
    log.info("hand-over for call %s: ringing %s", call, mask(phone))
    return dial_on_duty(
        phone,
        ring=handover_ring_seconds(),
        result_url=voice_url("handoff-result", call),
        answered_url=voice_url("handoff-answered", call, user=str(user)),
        transcript_url=voice_url("handoff-transcript", call),
    )


@router.post("/voice/handoff-answered")
async def handoff_answered(
    call: uuid.UUID, user: uuid.UUID, _: Params, session: Db
) -> Response:
    """The on-duty phone picked up (04 §4.4 step 5): the incident is taken by the one we
    rang, and Twilio connects the two. Nothing to say."""
    try:
        row = await answer_handover(session, call, True)
        if row is not None and not await take_for_handover(
            session, row.senior_id, user
        ):
            log.info("hand-over for call %s: no open incident to take", call)
        await session.commit()
    except SQLAlchemyError, OSError:
        # Still connect them: DAS is on the line.
        log.exception("hand-over answer for call %s: database unavailable", call)
    return twiml("")


@router.post("/voice/handoff-result")
async def handoff_result(call: uuid.UUID, params: Params, session: Db) -> Response:
    """The dial to DAS finished (04 §4.4 step 6). Not answered: the senior hears that
    someone will call back, and the incident stays open on the dashboard (UC-07)."""
    status = params.get("DialCallStatus", "")
    log.info("hand-over for call %s: dial %s", call, status)
    if status == "completed":
        return hangup()
    try:
        await answer_handover(session, call, False)
        if not hung_up(params):
            await agent_turn(session, call, CALL_BACK)
        await session.commit()
    except SQLAlchemyError, OSError:
        log.exception("hand-over result for call %s: database unavailable", call)
    return twiml(f"{STOP_TRANSCRIPTION}{say(CALL_BACK)}<Hangup/>")


@router.post("/voice/handoff-transcript", status_code=204)
async def handoff_transcript(call: uuid.UUID, params: Params, session: Db) -> Response:
    """The hand-over's talk, one final sentence at a time, stored as the senior's or
    the DAS employee's turn in the order it arrives (04 §4.4 step 5). A failed
    transcription is a system turn, so the transcript says why the talk is missing."""
    line = transcribed(params)
    if params.get("TranscriptionEvent") == "transcription-error":
        code = params.get("TranscriptionErrorCode", "")
        log.warning(
            "hand-over transcription for call %s failed: %s %s",
            call,
            code,
            params.get("TranscriptionError", ""),
        )
        line = (Speaker.system, f"{TRANSCRIPTION_FAILED} (eroare Twilio {code}).", None)
    if line is None:
        return Response(status_code=204)
    speaker, words, confidence = line
    try:
        if not await append_turn(
            session, call, speaker, TurnKind.speech, words, confidence=confidence
        ):
            log.warning("hand-over transcript for unknown call %s", call)
        await session.commit()
    except SQLAlchemyError, OSError:
        log.exception("hand-over transcript for call %s: database unavailable", call)
    return Response(status_code=204)


@router.websocket("/voice/relay")
async def relay(ws: WebSocket, call: uuid.UUID) -> None:
    """One ConversationRelay session (04 §4.3). Closing before accept answers the
    upgrade with 403, so an unsigned connect gets nothing.

    The signature covers only the address, so it is the same for every connect to one
    call; `serve` makes the call id one-time (01 §4 channel 7).
    """
    urls = [public_url(ws.url.path, ws.url.query, s) for s in ("wss", "https")]
    if not signed(ws.headers.get("x-twilio-signature", ""), urls, []):
        log.warning("refused not_allowed: unsigned relay connect, call %s", call)
        await ws.close(code=1008)
        return
    # The session holds no database session (ADR-004), so its greeting is read here.
    async with Session() as session:
        context = await answer_context(session, call, notes=True)
    if context is None:
        log.warning("relay connect for unknown call %s", call)
        await ws.close(code=1008)
        return
    start = (
        echo_for(call, context.greeting)
        if context.trigger is CallTrigger.test
        else agent_for(call, context)
    )
    await serve(ws, call, start)


KEY_9_REASON = "A cerut un operator (tasta 9)"
ALARM_REASON = "A spus: «{words}»"
HUMAN_REASON = "A cerut un operator"
REASON_ROOM = 200  # Call.reason's length


@cache  # one client for every call, so a call's first round reuses its connections
def model_stream() -> ModelStream:
    s = get_settings()
    return stream_with(deepinfra_model(s.deepinfra_api_key, s.agent_model))


def echo_for(call: uuid.UUID, greeting: str) -> Callable[[Send], Handler]:
    """A test call keeps the scripted echo and never hands over (05 §1)."""

    def start(send: Send) -> Handler:
        return Echo(Relay(greeting, partial(save_turn, call)), send, call)

    return start


def agent_for(call: uuid.UUID, context: AnswerContext) -> Callable[[Send], Handler]:
    """The agent, with its writes composed here: `agent` can't import `calls`."""

    async def answer(q, a) -> None:
        await save_answer(call, q, a.value, clear=a.clear, quote=a.words)

    async def end(summary: str, dropped: bool) -> None:
        await end_wellbeing(call, summary, dropped=dropped)

    line = Line(
        store=partial(save_turn, call),
        answer=answer,
        concern=partial(save_concern, call),
        hand_over=hand_over_for(call),
        end=end,
    )

    def start(send: Send) -> Handler:
        return Agent(
            call=str(call),
            greeting=context.greeting,
            form_of_address=context.form_of_address,
            heat=context.heat,
            follow_up=context.follow_up,
            how_to_talk=context.how_to_talk,
            send=send,
            line=line,
            model=model_stream(),
        )

    return start


def hand_over_for(call: uuid.UUID) -> HandOver:
    """The session's way to start a hand-over: `agent` can't import `calls`, and a
    router may import anything (04 §4.3, 04 §5)."""

    async def hand_over(escalation: Escalation, words: str) -> bool:
        match escalation:
            case Escalation.key_9:
                source, reason = ReportSource.request_human, KEY_9_REASON
            case Escalation.alarm | Escalation.tier_2:
                room = REASON_ROOM - len(ALARM_REASON.format(words=""))
                reason = ALARM_REASON.format(words=words[:room])
                source = (
                    ReportSource.alarm_tier1
                    if escalation is Escalation.alarm
                    else ReportSource.alarm_tier2
                )
            case Escalation.concern:
                source, reason = ReportSource.raise_concern, words[:REASON_ROOM]
            case Escalation.human:
                source = ReportSource.request_human
                reason = words[:REASON_ROOM] or HUMAN_REASON
            case Escalation.rules:
                source, reason = ReportSource.rules, None
        return await begin_handover(call, source, reason)

    return hand_over
