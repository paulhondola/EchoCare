"""The dialer: hands queued calls that have come due to Twilio (06 §1, G9).

A call is dialed in id order, up to `max_live_calls` live calls, and only to a number on
the allowlist. `dialed_at` is committed before Twilio is asked, so a call is dialed once
at most: a timeout leaves it queued with its stamp, and its status callback settles it.
"""

import logging
from datetime import datetime

import httpx
from sqlalchemy import and_, func, or_, select

from app.calls.ending import settle
from app.core.db import Session
from app.core.settings import get_settings
from app.seniors.models import EnrollmentState, Senior
from app.voice.calls import LIVE, CallState
from app.voice.models import Call, CallTrigger
from app.voice.service import store_sid, take_for_dialing
from app.voice.twilio import configured, dial, dial_allowed, refused

log = logging.getLogger("echocare.dialer")

# Whom each kind of call may ring: a `test` call is place_call.py's, never picked here.
DIALABLE = {
    CallTrigger.campaign: EnrollmentState.active,
    CallTrigger.watch: EnrollmentState.active,
    CallTrigger.manual: EnrollmentState.active,
    CallTrigger.welcome: EnrollmentState.accepted,
}


async def dial_due(now: datetime) -> int:
    """Dials the calls due at `now`; how many Twilio took."""
    if not configured():
        return 0
    placed = 0
    async with Session() as session:
        live = await session.scalar(
            select(func.count()).where(
                Call.state.in_(LIVE), Call.dialed_at.is_not(None)
            )
        )
        free = get_settings().max_live_calls - live
        if free <= 0:
            return 0
        due = await session.execute(
            select(Call.id, Call.trigger, Senior.phone_e164)
            .join(Senior, Senior.id == Call.senior_id)
            .where(
                Call.state == CallState.queued,
                Call.dialed_at.is_(None),
                Call.due_at <= now,
                or_(
                    *(
                        and_(Call.trigger == trigger, Senior.enrollment_state == state)
                        for trigger, state in DIALABLE.items()
                    )
                ),
            )
            .order_by(Call.id)
        )
        # The allowlist comes before the free lines: calls it refuses must not hold them.
        wanted = []
        for call_id, trigger, phone in due:
            if dial_allowed(phone):
                wanted.append((call_id, trigger, phone))
            else:
                log.debug("call %s: not on the dial allowlist", call_id)
        for call_id, trigger, phone in wanted[:free]:
            if not await take_for_dialing(session, call_id, now):
                continue
            await session.commit()
            answer = "welcome" if trigger is CallTrigger.welcome else "answer"
            try:
                sid = await dial(phone, call_id, answer)
            except httpx.HTTPError as e:
                if refused(e):
                    log.warning("call %s: Twilio refused: %s", call_id, e)
                    await settle(session, call_id, None, CallState.failed)
                else:
                    # Twilio may have placed it; its callback settles it, or the sweep.
                    log.warning("call %s: dial outcome unknown: %r", call_id, e)
                continue
            await store_sid(session, call_id, sid)
            await session.commit()
            placed += 1
    return placed
