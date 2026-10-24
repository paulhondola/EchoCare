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
from app.voice.calls import LIVE, TWILIO_STATUSES, CallState, answered_by_machine
from app.voice.models import Call
from app.voice.twilio import CALL_LIMIT_SECONDS, RING_SECONDS, fetch_call, hang_up

log = logging.getLogger("echocare.sweep")

STUCK_AFTER = timedelta(seconds=RING_SECONDS + CALL_LIMIT_SECONDS, minutes=1)
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
                    try:
                        status, by = await fetch_call(sid)
                        if status in TWILIO_LIVE:
                            await hang_up(
                                sid, "queued" if status == "initiated" else status
                            )
                            status, by = await fetch_call(sid)
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code != 404:
                            raise
                        # Twilio has no such call, and never will.
                        log.warning("call %s: Twilio does not know its sid", call_id)
                        status = None
                        moved = await settle(
                            session, call_id, sid, CallState.failed, only_from=state
                        )
                    else:
                        # A voicemail whose /voice/amd callback was lost reads
                        # `completed`; on time it ends `unanswered` (04 §4.2).
                        new = (
                            CallState.unanswered
                            if by and answered_by_machine(by)
                            else TWILIO_STATUSES.get(status)
                        )
                        moved = await settle(session, call_id, sid, new)
        except Exception:
            log.exception("sweep of call %s failed", call_id)
            continue
        if moved is not None:
            settled += 1
            log.warning(
                "swept call %s: %s -> %s (Twilio %s)", call_id, state, moved, status
            )
    return settled
