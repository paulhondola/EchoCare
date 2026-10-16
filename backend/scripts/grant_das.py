"""Grant the DAS role to a phone number: the setup script of G6.

Run it inside the api container (locally `docker compose exec api`, on Railway
`railway ssh -s api -e staging`):

    python scripts/grant_das.py "Ana Pop" 0722123456
"""

import asyncio
import sys
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import Session
from app.core.phones import is_mobile, normalize
from app.models import Role
from app.staff.service import grant_staff


async def grant_das(display_name: str, phone: str) -> str:
    """Returns granted, already granted, or invalid, validating like POST /staff (§3.4)."""
    name = display_name.strip()
    if not 1 <= len(name) <= 120:
        return "invalid"
    try:
        e164 = normalize(phone)
    except ValueError:
        return "invalid"
    if not is_mobile(e164):  # no SMS, no sign-in
        return "invalid"
    async with Session() as session:
        user = await grant_staff(session, name, e164, Role.das, None, None)
    return "granted" if user else "already granted"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    result = asyncio.run(grant_das(sys.argv[1], sys.argv[2]))
    print(result)
    return 2 if result == "invalid" else 0


if __name__ == "__main__":
    sys.exit(main())
