"""The telephony edge (#15, spike S1): Twilio's callbacks and the relay WebSocket.

A scripted call with no model and no rules: a fixed Romanian greeting, what the person
says comes back as text and gets a fixed reply, and every turn is kept. Every callback
and the WebSocket connect are signature-checked (01 §4, channels 6 and 7).

The wellbeing call's agent, alarm phrases, the welcome call and hand-over build on
this; their callbacks join this router (04 §4.2).
"""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import parse_qsl
from xml.sax.saxutils import escape, quoteattr

import httpx
from fastapi import APIRouter, Depends, Request, Response, WebSocket
from fastapi.websockets import WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import refuse
from app.calls import (
    ENDED,
    TWILIO_STATUSES,
    CallState,
    after_callback,
    answered_by_machine,
)
from app.db import Session, get_session
from app.models import Call, CallTurn, Senior, Speaker, TurnKind
from app.settings import get_settings
from app.twilio import hang_up, public_url, signed, voice_url

log = logging.getLogger("sentinela.voice")

router = APIRouter()

LANGUAGE = "ro-RO"
GOODBYE = "Vă mulțumesc. La revedere."
SORRY = "Ne pare rău, apelul nu poate continua. La revedere."
# On the way to an ended call these states mean someone picked up (03 §9).
ANSWERED = frozenset(
    {CallState.in_progress, CallState.completed, CallState.handed_over}
)


def greeting(form_of_address: str) -> str:
    """The test call's opening (04 §4.2's greeting, minus the warning and the question)."""
    return (
        f"Bună ziua, {form_of_address}. Sunt asistentul automat al DAS Timișoara. "
        "Acesta este un apel de probă. Nu vă cer niciodată bani sau date. "
        "Spuneți ceva și vă repet ce am auzit. Apăsați zero ca să închideți."
    )


def heard(words: str) -> str:
    return f"Am auzit: {words.rstrip('.!?')}. Mai spuneți ceva?"


def twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(xml, media_type="text/xml")


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
    await session.commit()
    return moved


@router.post("/voice/answer")
async def answer(call: uuid.UUID, _: Params, session: Db) -> Response:
    """Picked up: connect to ConversationRelay in ro-RO (04 §4.2)."""
    form_of_address = await session.scalar(
        select(Senior.form_of_address)
        .join(Call, Call.senior_id == Senior.id)
        .where(Call.id == call)
    )
    if form_of_address is None:
        log.warning("answer for unknown call %s", call)
        return twiml(
            f"<Say language={quoteattr(LANGUAGE)}>{escape(SORRY)}</Say><Hangup/>"
        )
    s = get_settings()
    attrs = {
        "url": voice_url("relay", call, scheme="wss"),
        "language": LANGUAGE,
        "ttsProvider": s.twilio_tts_provider,
        "voice": s.twilio_voice,
        "welcomeGreeting": greeting(form_of_address),
        "dtmfDetection": "true",
    }
    relay = "".join(f" {name}={quoteattr(value)}" for name, value in attrs.items())
    return twiml(f"<Connect><ConversationRelay{relay}/></Connect>")


@router.post("/voice/status", status_code=204)
async def status(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Rings, answered, completed, not answered, busy, failed (04 §4.2)."""
    twilio_status = params.get("CallStatus", "")
    log.info("call %s: Twilio status %s", call, twilio_status)
    await move_call(
        session, call, params.get("CallSid"), TWILIO_STATUSES.get(twilio_status)
    )
    return Response(status_code=204)


@router.post("/voice/amd", status_code=204)
async def amd(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Voicemail detection: a machine is ended and counted as unanswered (04 §4.2)."""
    answered_by = params.get("AnsweredBy", "")
    log.info("call %s: answered by %s", call, answered_by)
    if not answered_by_machine(answered_by):
        return Response(status_code=204)
    moved = await move_call(session, call, params.get("CallSid"), CallState.unanswered)
    sid = params.get("CallSid")
    if moved is CallState.unanswered and sid:
        try:
            await hang_up(sid)
        except httpx.HTTPError:
            log.warning(
                "call %s: could not hang up on the machine", call, exc_info=True
            )
    return Response(status_code=204)


Store = Callable[[Speaker, TurnKind, str], Awaitable[None]]


class Relay:
    """The scripted side of one relay session (04 §4.3): what to send back for each
    message from Twilio. Kept apart from the WebSocket, so a script of messages
    tests it with no phone and no database (06 §5)."""

    def __init__(self, greeting: str, store: Store) -> None:
        self.greeting = greeting
        self.store = store

    async def say(self, text: str) -> list[dict[str, Any]]:
        await self.store(Speaker.agent, TurnKind.speech, text)
        return [{"type": "text", "token": text, "last": True}]

    async def handle(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        match message.get("type"):
            case "setup":
                # Twilio speaks the greeting itself, from the TwiML; keep it in the transcript.
                await self.store(Speaker.agent, TurnKind.speech, self.greeting)
                return []
            case "prompt":
                if message.get("last") is False:  # a partial, if ever turned on
                    return []
                words = str(message.get("voicePrompt", "")).strip()
                log.info("heard: %s", words)
                await self.store(Speaker.senior, TurnKind.speech, words)
                return await self.say(heard(words))
            case "dtmf":
                digit = str(message.get("digit", ""))
                log.info("key: %s", digit)
                await self.store(Speaker.senior, TurnKind.keys, digit)
                if digit == "0":
                    return [*await self.say(GOODBYE), {"type": "end"}]
                return await self.say(f"Ați apăsat tasta {digit}.")
            case "interrupt":
                spoken = str(message.get("utteranceUntilInterrupt", ""))
                await self.store(
                    Speaker.system, TurnKind.speech, f"interrupted after: {spoken}"
                )
                return []
            case "error":
                description = str(message.get("description", ""))
                log.warning("relay error: %s", description)
                await self.store(
                    Speaker.system, TurnKind.speech, f"error: {description}"
                )
                return []
            case other:
                log.info("relay: ignored message type %s", other)
                return []


@router.websocket("/voice/relay")
async def relay(ws: WebSocket, call: uuid.UUID) -> None:
    """One ConversationRelay session (04 §4.3). Closing before accept answers the
    upgrade with 403, so an unsigned connect gets nothing."""
    urls = [public_url(ws.url.path, ws.url.query, s) for s in ("wss", "https")]
    if not signed(ws.headers.get("x-twilio-signature", ""), urls, []):
        log.warning("refused not_allowed: unsigned relay connect, call %s", call)
        await ws.close(code=1008)
        return
    async with Session() as session:
        row = (
            await session.execute(
                select(Call.twilio_call_id, Senior.form_of_address)
                .join(Senior, Senior.id == Call.senior_id)
                .where(Call.id == call)
            )
        ).first()
        if row is None:
            log.warning("relay connect for unknown call %s", call)
            await ws.close(code=1008)
            return
        # Continues the transcript if Twilio reconnects the same call.
        position = await session.scalar(
            select(func.coalesce(func.max(CallTurn.position) + 1, 0)).where(
                CallTurn.call_id == call
            )
        )

        async def store(speaker: Speaker, kind: TurnKind, content: str) -> None:
            nonlocal position
            session.add(
                CallTurn(
                    call_id=call,
                    position=position,
                    speaker=speaker,
                    kind=kind,
                    content=content,
                )
            )
            position += 1
            await session.commit()

        session_relay = Relay(greeting(row.form_of_address), store)
        await ws.accept()
        log.info("relay open: call %s", call)
        try:
            while True:
                try:
                    message = json.loads(await ws.receive_text())
                except ValueError:
                    log.warning("relay: a message that is not JSON, call %s", call)
                    continue
                sid = message.get("callSid")
                if message.get("type") == "setup" and row.twilio_call_id not in (
                    None,
                    sid,
                ):
                    log.warning(
                        "relay: call %s is Twilio's %s, not %s",
                        call,
                        row.twilio_call_id,
                        sid,
                    )
                    await ws.close(code=1008)
                    return
                for reply in await session_relay.handle(message):
                    await ws.send_json(reply)
        except WebSocketDisconnect:
            log.info("relay closed: call %s", call)
