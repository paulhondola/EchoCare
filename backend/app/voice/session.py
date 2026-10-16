"""One ConversationRelay session (04 §4.3), once the router has checked the connect's
signature: the live call it belongs to, its transcript, and the call's end.

The call id is one-time as 01 §4 channel 7 asks: a connect is taken only while the
call is live, and nothing before a `setup` naming the call's Twilio id.
"""

import json
import logging
import uuid
from typing import Any, Protocol

from fastapi.websockets import WebSocketDisconnect
from sqlalchemy import func, select

from app.core.db import Session
from app.seniors.models import Senior
from app.voice.calls import LIVE, CallState
from app.voice.dialogue import Relay, greeting
from app.voice.models import Call, CallTurn, Speaker, TurnKind
from app.voice.service import move_call

log = logging.getLogger("echocare.voice")


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
        row = (
            await session.execute(
                select(Call.twilio_call_id, Senior.form_of_address)
                .join(Senior, Senior.id == Call.senior_id)
                .where(Call.id == call, Call.state.in_(LIVE))
            )
        ).first()
        if row is None:
            log.warning("relay connect for unknown or ended call %s", call)
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
                    await move_call(session, call, None, CallState.completed)
                for reply in replies:
                    await ws.send_json(reply)
        except WebSocketDisconnect:
            log.info("relay closed: call %s", call)
