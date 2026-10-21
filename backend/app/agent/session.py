"""One ConversationRelay session (04 §4.3), once the router has checked the connect's
signature: the live call it belongs to, its transcript, and the call's end.

The call id is one-time as 01 §4 channel 7 asks: a connect is taken only while the
call is live, and nothing before a `setup` naming the call's Twilio id. It reads and
writes the call only through `voice` (ADR-004, ADR-005), so it can later leave the
process.
"""

import json
import logging
import uuid
from typing import Any, Protocol

from fastapi.websockets import WebSocketDisconnect

from app.agent.relay import Relay
from app.core.db import Session
from app.voice.calls import CallState
from app.voice.dialogue import greeting
from app.voice.models import Speaker, TurnKind
from app.voice.service import add_turn, live_call, next_turn_position, transition

log = logging.getLogger("echocare.agent")


class Socket(Protocol):
    """What a session needs of its WebSocket, so a test can script one (06 §5).
    Closing before accept answers the upgrade with 403."""

    async def accept(self) -> None: ...

    async def receive_text(self) -> str: ...

    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int) -> None: ...


async def serve(ws: Socket, call: uuid.UUID) -> None:
    """Runs the session until Twilio disconnects or the call's own setup is missing."""
    async with Session() as session:
        row = await live_call(session, call)
        if row is None:
            log.warning("relay connect for unknown or ended call %s", call)
            await ws.close(code=1008)
            return
        # Continues the transcript if Twilio reconnects the same call.
        position = await next_turn_position(session, call)

        async def store(speaker: Speaker, kind: TurnKind, content: str) -> None:
            nonlocal position
            add_turn(session, call, position, speaker, kind, content)
            position += 1
            await session.commit()

        session_relay = Relay(greeting(row.form_of_address), store)
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
                    log.warning(
                        "relay: a message that is not a JSON object, call %s", call
                    )
                    continue
                if not set_up:
                    sid = message.get("callSid")
                    if message.get("type") != "setup" or row.twilio_call_id not in (
                        None,
                        sid,
                    ):
                        log.warning(
                            "relay: call %s is Twilio's %s; got %s from %s",
                            call,
                            row.twilio_call_id,
                            message.get("type"),
                            sid,
                        )
                        await ws.close(code=1008)
                        return
                    set_up = True
                replies = await session_relay.handle(message)
                if any(reply["type"] == "end" for reply in replies):
                    # We close it, so it ends completed even if they hang up during
                    # the goodbye; a hang-up before this ends dropped (03 §9).
                    await transition(session, call, None, CallState.completed)
                    await session.commit()
                for reply in replies:
                    await ws.send_json(reply)
        except WebSocketDisconnect:
            log.info("relay closed: call %s", call)
