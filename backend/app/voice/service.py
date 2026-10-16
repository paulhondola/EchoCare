import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.voice.calls import ENDED, CallState, after_callback
from app.voice.dialogue import ANSWERED
from app.voice.models import Call

log = logging.getLogger("sentinela.voice")


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
    elif new is not None and new is not call.state:
        log.info("call %s: %s ignored in %s", call_id, new, call.state)
    await session.commit()
    return moved
