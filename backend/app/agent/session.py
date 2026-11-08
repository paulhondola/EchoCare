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
from collections.abc import Callable
from typing import Any, Protocol

from fastapi.websockets import WebSocketDisconnect

from app.agent.loop import Send
from app.agent.relay import Relay
from app.voice.service import end_completed, open_line

# Under echocare.voice, where the relay logged before it moved here (ADR-005).
log = logging.getLogger("echocare.voice.agent")


class Socket(Protocol):
    """What a session needs of its WebSocket, so a test can script one (06 §5).
    Closing before accept answers the upgrade with 403."""

    async def accept(self) -> None: ...

    async def receive_text(self) -> str: ...

    async def send_json(self, data: Any) -> None: ...

    async def close(self, code: int) -> None: ...


class Handler(Protocol):
    """What a session drives: every message in, and `close` once the line is gone."""

    async def handle(self, message: dict[str, Any]) -> None: ...

    async def close(self) -> None: ...


class Echo:
    """The scripted echo (04 §4.3), kept for test calls (05 §1)."""

    def __init__(self, relay: Relay, send: Send, call: uuid.UUID) -> None:
        self.relay, self.send, self.call = relay, send, call

    async def handle(self, message: dict[str, Any]) -> None:
        replies = await self.relay.handle(message)
        # We close it, so it ends completed even if they hang up during the
        # goodbye; a hang-up before this ends dropped (03 §9).
        if any(r["type"] == "end" and "handoffData" not in r for r in replies):
            await end_completed(self.call)
        for reply in replies:
            await self.send(reply)

    async def close(self) -> None:
        pass


async def serve(ws: Socket, call: uuid.UUID, start: Callable[[Send], Handler]) -> None:
    """Runs the session until Twilio disconnects or the call's own setup is missing.
    `start` builds the handler once the socket is accepted."""
    line = await open_line(call)
    if line is None:
        log.warning("relay connect for unknown or ended call %s", call)
        await ws.close(code=1008)
        return

    await ws.accept()
    handler = start(ws.send_json)
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
            await handler.handle(message)
    except WebSocketDisconnect:
        log.info("relay closed: call %s", call)
        # Waits for in-flight writes, so Twilio's completed finds them stored.
        await handler.close()
