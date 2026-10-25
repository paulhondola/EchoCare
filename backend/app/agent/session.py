"""One ConversationRelay session (04 §4.3), once the router has checked the connect's
signature: the live call it belongs to, its transcript, and the call's end.

The call id is one-time as 01 §4 channel 7 asks: a connect is taken only while the
call is live, and nothing before a `setup` naming the call's Twilio id. It reads and
writes the call only through `voice`'s session-owning calls and holds no database
session (ADR-004, ADR-005), so it can later leave the process.
"""

import json
import logging
import uuid
from typing import Any, Protocol

from fastapi.websockets import WebSocketDisconnect

from app.agent.relay import Relay
from app.voice.models import Speaker, TurnKind
from app.voice.service import end_completed, open_line, save_turn

# Under echocare.voice, where the relay logged before it moved here (ADR-005).
log = logging.getLogger("echocare.voice.agent")


class Socket(Protocol):
    """What a session needs of its WebSocket, so a test can script one (06 §5).
    Closing before accept answers the upgrade with 403."""

    async def accept(self) -> None: ...

    async def receive_text(self) -> str: ...

    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int) -> None: ...


async def serve(ws: Socket, call: uuid.UUID, greeting: str) -> None:
    """Runs the session until Twilio disconnects or the call's own setup is missing."""
    line = await open_line(call)
    if line is None:
        log.warning("relay connect for unknown or ended call %s", call)
        await ws.close(code=1008)
        return
    position = line.next_position

    async def store(speaker: Speaker, kind: TurnKind, content: str) -> None:
        nonlocal position
        await save_turn(call, position, speaker, kind, content)
        position += 1

    session_relay = Relay(greeting, store)
    await ws.accept()
    log.info("relay open: call %s", call)
    set_up = False
    try:
        while True:
            try:
                message = json.loads(await ws.receive_text())
            except ValueError:
                message = None
            if not isinstance(message, dict):
                log.warning("relay: a message that is not a JSON object, call %s", call)
                continue
            if not set_up:
                sid = message.get("callSid")
                if message.get("type") != "setup" or line.twilio_call_id not in (
                    None,
                    sid,
                ):
                    log.warning(
                        "relay: call %s is Twilio's %s; got %s from %s",
                        call,
                        line.twilio_call_id,
                        message.get("type"),
                        sid,
                    )
                    await ws.close(code=1008)
                    return
                set_up = True
            replies = await session_relay.handle(message)
            if any(reply["type"] == "end" for reply in replies):
                # We close it, so it ends completed even if they hang up during the
                # goodbye; a hang-up before this ends dropped (03 §9).
                await end_completed(call)
            for reply in replies:
                await ws.send_json(reply)
    except WebSocketDisconnect:
        log.info("relay closed: call %s", call)
