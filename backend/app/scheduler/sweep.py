"""The sweep: settles calls the dialer handed to Twilio that nothing has ended (06 §1).

A call is stuck when it is still live well past ring time, the longest call and a minute
to spare, so no status callback is coming. Twilio is asked what became of it, hung up if
it still has the call live, and the answer is applied as a status callback would.
"""

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from app.calls.ending import settle
from app.core.db import Session
from app.voice.calls import LIVE, TWILIO_STATUSES, CallState
from app.voice.models import Call
from app.voice.twilio import RING_SECONDS, fetch_status, hang_up

log = logging.getLogger("echocare.sweep")

STUCK_AFTER = (
    timedelta(seconds=RING_SECONDS) + timedelta(minutes=3) + timedelta(minutes=1)
)
# Twilio statuses of a call that is not over; `initiated` is hung up as `queued`.
TWILIO_LIVE = frozenset({"queued", "initiated", "ringing", "in-progress"})


async def sweep(now: datetime) -> int:
    """Settles the stuck calls at `now`; how many it moved."""
    async with Session() as session:
        stuck = (
            await session.execute(
                select(Call.id, Call.twilio_call_id, Call.state)
                .where(Call.state.in_(LIVE), Call.dialed_at < now - STUCK_AFTER)
                .order_by(Call.id)
            )
        ).all()
    settled = 0
    # A session per call: no transaction is held across a Twilio request.
    for call_id, sid, state in stuck:
        try:
            async with Session() as session:
                if sid is None:
                    # Timed out dialing and no callback since: Twilio never had it.
                    status = None
                    moved = await settle(
                        session, call_id, None, CallState.failed, only_from=state
                    )
                else:
                    status = await fetch_status(sid)
                    if status in TWILIO_LIVE:
                        await hang_up(
                            sid, "queued" if status == "initiated" else status
                        )
                        status = await fetch_status(sid)
                    moved = await settle(
                        session, call_id, sid, TWILIO_STATUSES.get(status)
                    )
        except httpx.HTTPError as e:
            log.warning("sweep of call %s failed: %r", call_id, e)
            continue
        if moved is not None:
            settled += 1
            log.warning(
                "swept call %s: %s -> %s (Twilio %s)", call_id, state, moved, status
            )
    return settled
