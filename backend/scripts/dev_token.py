"""Print a real Firebase identity token for a test number, to call the API by hand.

Signs in the way the apps do, through Firebase's REST API with the public web key, so
it needs no service account (auth-layer AL11). Only the test numbers in the Firebase
console work, with their fixed codes (backend/README.md). From backend/:

    uv run python scripts/dev_token.py +40700000001 111111

Paste the token into Authorize at /api/docs, or use it with curl. It lasts an hour.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.phones import normalize

ACCOUNTS_URL = "https://identitytoolkit.googleapis.com/v1/accounts:{}?key={}"


def _read_env_key(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() in (
            "FIREBASE_WEB_API_KEY",
            "VITE_FIREBASE_API_KEY",
            "WEB_API_KEY",
        ):
            val = v.strip().strip("'\"")
            if val:
                return val
    return None


def get_web_api_key(env_path: Path | None = None) -> str:
    """Read the Firebase web API key from the environment or .env files."""
    for var in ("FIREBASE_WEB_API_KEY", "VITE_FIREBASE_API_KEY", "WEB_API_KEY"):
        if val := os.environ.get(var):
            return val

    if env_path is not None:
        if val := _read_env_key(env_path):
            return val
        raise SystemExit(
            f"FIREBASE_WEB_API_KEY is not set in {env_path} or environment. "
            "See backend/.env.example."
        )

    backend_root = Path(__file__).resolve().parent.parent
    candidates = [
        backend_root / ".env",
        backend_root.parent / "dashboard" / ".env",
        Path.cwd() / ".env",
    ]
    for candidate in candidates:
        if val := _read_env_key(candidate):
            return val

    raise SystemExit(
        "FIREBASE_WEB_API_KEY is not set in backend/.env, dashboard/.env or environment. "
        "See backend/.env.example."
    )


def call(method: str, body: dict, api_key: str | None = None) -> dict:
    key = api_key or get_web_api_key()
    request = urllib.request.Request(
        ACCOUNTS_URL.format(method, key),
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
    api_key = get_web_api_key()
    phone, code = normalize(sys.argv[1]), sys.argv[2]
    # Test numbers skip the reCAPTCHA check, so any token string passes.
    sent = call(
        "sendVerificationCode",
        {"phoneNumber": phone, "recaptchaToken": "dev"},
        api_key=api_key,
    )
    signed_in = call(
        "signInWithPhoneNumber",
        {"sessionInfo": sent["sessionInfo"], "code": code},
        api_key=api_key,
    )
    print(signed_in["idToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
