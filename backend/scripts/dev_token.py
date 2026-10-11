"""Print a real Firebase identity token for a test number, to call the API by hand.

Signs in the way the apps do, through Firebase's REST API with the public web key, so
it needs no service account (auth-layer AL11). Only the test numbers in the Firebase
console work, with their fixed codes (backend/README.md). From backend/:

    uv run python scripts/dev_token.py +40700000001 111111

Paste the token into Authorize at /api/docs, or use it with curl. It lasts an hour.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.phones import normalize

# Public: the dashboard ships it in every browser bundle (.railway/railway.ts).
WEB_API_KEY = "AIzaSyBWFvTyqk904SsoT_uFXIzXgyHBBxhz5m0"
ACCOUNTS = "https://identitytoolkit.googleapis.com/v1/accounts:{}?key=" + WEB_API_KEY


def call(method: str, body: dict) -> dict:
    request = urllib.request.Request(
        ACCOUNTS.format(method),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        # Firebase says why in the body, for example INVALID_CODE.
        raise SystemExit(f"{method}: {json.load(e)['error']['message']}") from None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    phone, code = normalize(sys.argv[1]), sys.argv[2]
    # Test numbers skip the reCAPTCHA check, so any token string passes.
    sent = call("sendVerificationCode", {"phoneNumber": phone, "recaptchaToken": "dev"})
    signed_in = call(
        "signInWithPhoneNumber", {"sessionInfo": sent["sessionInfo"], "code": code}
    )
    print(signed_in["idToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
