"""Place a scripted test call to a registered senior's number (#15, spike S1).

A script, not an endpoint: an endpoint would stay in the API for old clients. The
senior must exist (POST /api/seniors); the call is a `test` one on their record.
Twilio must reach PUBLIC_BASE_URL, so run it inside the api container: locally with
the tunnel profile (`docker compose exec api`), on staging through
`railway ssh -s api -e staging`:

    python scripts/place_call.py 0722123456
"""

import asyncio
import sys
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.db import Session
from app.core.phones import normalize
from app.core.settings import get_settings
from app.models import Call, CallTrigger, Senior
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.twilio import dial


async def place_call(phone: str) -> tuple[bool, str]:
    """Whether the call was placed, and what to print."""
    try:
        e164 = normalize(phone)
    except ValueError:
        return False, "invalid number"
    s = get_settings()
    if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number):
        return False, "set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER"
    async with Session() as session:
        senior = await session.scalar(
            select(Senior).where(Senior.phone_e164 == e164).order_by(Senior.created_at)
        )
        if senior is None:
            return (
                False,
                "no senior has this number: register one with POST /api/seniors",
            )
        call = Call(
            senior_id=senior.id,
            trigger=CallTrigger.test,
            starting_severity=Severity.yellow,  # like a request for a call (UC-10)
            due_at=func.now(),
        )
        session.add(call)
        try:
            await session.commit()
        except IntegrityError:  # never two live calls for one senior (05 §3)
            return False, "a call is already live for this senior"
        try:
            sid = await dial(e164, call.id)
        except httpx.HTTPError as e:
            call.state = CallState.failed
            call.ended_at = func.now()
            await session.commit()
            return False, f"Twilio refused the call: {e}"
        # A status callback may have stored it first; it is the same id.
        call.twilio_call_id = sid
        await session.commit()
    return True, f"placed call {call.id} (Twilio {sid}) to {senior.form_of_address}"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    placed, message = asyncio.run(place_call(sys.argv[1]))
    print(message)
    return 0 if placed else 1


if __name__ == "__main__":
    sys.exit(main())
