"""Print a real Firebase identity token for a phone number, to call the API by hand.

Needs the laptop key in backend/.env as FIREBASE_SERVICE_ACCOUNT (auth-layer AL10).
From backend/:

    uv run python scripts/dev_token.py +40700000001

Paste the token into Authorize at /api/docs, or use it with curl. It lasts an hour.
"""

import json
import sys
import urllib.request
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firebase_admin import auth

from app.auth import init_firebase
from app.phones import normalize
from app.settings import get_settings

# Public: the dashboard ships it in every browser bundle (.railway/railway.ts).
WEB_API_KEY = "AIzaSyBWFvTyqk904SsoT_uFXIzXgyHBBxhz5m0"
EXCHANGE = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    f"?key={WEB_API_KEY}"
)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    service_account = get_settings().firebase_service_account
    if not service_account:
        print("Set FIREBASE_SERVICE_ACCOUNT in backend/.env first.", file=sys.stderr)
        return 2
    init_firebase(service_account)
    phone = normalize(sys.argv[1])
    try:
        uid = auth.get_user_by_phone_number(phone).uid
    except auth.UserNotFoundError:
        uid = auth.create_user(phone_number=phone).uid
    custom = auth.create_custom_token(uid).decode()
    request = urllib.request.Request(
        EXCHANGE,
        data=json.dumps({"token": custom, "returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        print(json.load(response)["idToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
