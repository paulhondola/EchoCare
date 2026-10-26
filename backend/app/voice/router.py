import logging
import uuid
from typing import Annotated
from urllib.parse import parse_qsl
from xml.sax.saxutils import quoteattr

import httpx
from fastapi import APIRouter, Depends, Request, Response, WebSocket
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.session import serve
from app.auth.service import refuse
from app.calls.ending import settle
from app.core.db import get_session
from app.core.settings import get_settings
from app.voice.calls import (
    TWILIO_DIALING,
    TWILIO_STATUSES,
    CallState,
    answered_by_machine,
)
from app.voice.dialogue import LANGUAGE, greeting, sorry, twiml, welcome_standin
from app.voice.service import form_of_address, move_call
from app.voice.twilio import hang_up, public_url, signed, voice_url

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


@router.post("/voice/answer")
async def answer(call: uuid.UUID, _: Params, session: Db) -> Response:
    """Picked up: connect to ConversationRelay in ro-RO (04 §4.2)."""
    try:
        addressed = await form_of_address(session, call)
    except SQLAlchemyError, OSError:
        log.exception("answer for call %s: database unavailable", call)
        return sorry()
    if addressed is None:
        log.warning("answer for unknown call %s", call)
        return sorry()
    s = get_settings()
    attrs = {
        "url": voice_url("relay", call, scheme="wss"),
        "language": LANGUAGE,
        "ttsProvider": s.twilio_tts_provider,
        "voice": s.twilio_voice,
        "welcomeGreeting": greeting(addressed),
        "dtmfDetection": "true",
    }
    relay_tag = "".join(f" {name}={quoteattr(value)}" for name, value in attrs.items())
    return twiml(f"<Connect><ConversationRelay{relay_tag}/></Connect>")


@router.post("/voice/welcome")
async def welcome(call: uuid.UUID, params: Params, session: Db) -> Response:
    """Picked up: the stand-in welcome call says one sentence and hangs up (04 §4.2).
    The call is marked completed first, so Twilio's later completed callback leaves it
    completed rather than dropped (03 §9)."""
    try:
        addressed = await form_of_address(session, call)
        if addressed is None:
            log.warning("welcome for unknown call %s", call)
            return sorry()
        await move_call(session, call, params.get("CallSid"), CallState.completed)
    except SQLAlchemyError, OSError:
        log.exception("welcome for call %s: database unavailable", call)
        return sorry()
    return welcome_standin(addressed)


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
    await serve(ws, call)
