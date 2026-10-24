"""Talking to Twilio: request signatures (01 §4, channels 6 and 7) and the Voice API
(channel 5, 04 §4.1).

No Twilio library: the Voice API is two form posts through httpx, asynchronous like
everything in the request path (01 §8), and the signature is Twilio's documented HMAC,
a few lines here.
"""

import base64
import hashlib
import hmac
import logging
import re
import uuid
from collections.abc import Iterable

import httpx

from app.core.phones import mask
from app.core.settings import get_settings

log = logging.getLogger("echocare.twilio")

# How long the senior's phone rings before Twilio gives up (04 §4.1).
RING_SECONDS = 30
# The longest a call may run (04 §4.1, 06 §3); Twilio hangs up at the limit.
CALL_LIMIT_SECONDS = 180


def signature(auth_token: str, url: str, params: Iterable[tuple[str, str]]) -> str:
    """Twilio's X-Twilio-Signature: HMAC-SHA1 over the full URL Twilio called, then each
    POST parameter as name and value, sorted by name; base64."""
    payload = url + "".join(name + value for name, value in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def signed(header: str, urls: Iterable[str], params: list[tuple[str, str]]) -> bool:
    """Whether `header` is Twilio's signature for one of `urls`. Without an auth token,
    nothing is signed, so every callback is refused."""
    token = get_settings().twilio_auth_token
    if not token or not header:
        return False
    return any(
        hmac.compare_digest(header, signature(token, url, params)) for url in urls
    )


def public_url(path: str, query: str = "", scheme: str | None = None) -> str:
    """The address Twilio called, rebuilt from PUBLIC_BASE_URL: behind Railway's proxy,
    the request's own URL is not the one Twilio signed."""
    base = get_settings().public_base_url.rstrip("/")
    if scheme is not None:
        base = scheme + base[base.index(":") :]
    return base + path + (f"?{query}" if query else "")


def voice_url(path: str, call_id: uuid.UUID, scheme: str | None = None) -> str:
    """A callback address carrying our call id (04 §4.1)."""
    return public_url(f"/api/voice/{path}", f"call={call_id}", scheme)


def configured() -> bool:
    """Whether the account is set up enough to place a call."""
    s = get_settings()
    return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number)


def dial_allowed(phone_e164: str) -> bool:
    """Whether the scheduler may ring this number: `*` everyone, empty nobody."""
    allowed = get_settings().dial_allowlist
    return allowed == "*" or phone_e164 in allowed.split(",")


def refused(error: httpx.HTTPError) -> bool:
    """Whether Twilio answered with a 4xx, so retrying the same request cannot help."""
    return (
        isinstance(error, httpx.HTTPStatusError)
        and 400 <= error.response.status_code < 500
    )


async def dial(to: str, call_id: uuid.UUID, answer: str = "answer") -> str:
    """Asks Twilio to place the call (04 §4.1); Twilio's call id. `answer` is the
    callback path Twilio fetches on pickup: "answer" or "welcome". Raises
    httpx.HTTPError when Twilio refuses or cannot be reached."""
    s = get_settings()
    data = {
        "To": to,
        "From": s.twilio_from_number,
        "Url": voice_url(answer, call_id),
        "Method": "POST",
        "StatusCallback": voice_url("status", call_id),
        "StatusCallbackMethod": "POST",
        "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
        # In the background: the call connects at once and the result arrives later.
        "MachineDetection": "Enable",
        "AsyncAmd": "true",
        "AsyncAmdStatusCallback": voice_url("amd", call_id),
        "AsyncAmdStatusCallbackMethod": "POST",
        "Timeout": str(RING_SECONDS),
        "TimeLimit": str(CALL_LIMIT_SECONDS),
    }
    r = await _request("POST", "Calls.json", data)
    return r.json()["sid"]


async def fetch_call(sid: str) -> tuple[str, str | None]:
    """Twilio's own status for a call and who answered it (`answered_by`, set for calls
    placed with voicemail detection), to settle one whose callbacks never came."""
    body = (await _request("GET", f"Calls/{sid}.json")).json()
    return body["status"], body.get("answered_by")


async def hang_up(sid: str, status: str = "in-progress") -> None:
    """Ends a call, as when a machine answered (04 §4.2). One still queued or ringing is
    canceled; a live one is completed."""
    ended = "canceled" if status in ("queued", "ringing") else "completed"
    await _request("POST", f"Calls/{sid}.json", {"Status": ended})


async def _request(method: str, path: str, data: dict | None = None) -> httpx.Response:
    s = get_settings()
    async with httpx.AsyncClient(
        auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=10
    ) as client:
        r = await client.request(
            method,
            f"https://{s.twilio_api_host}/2010-04-01/Accounts/{s.twilio_account_sid}/{path}",
            data=data,
        )
    if r.is_error:
        # Twilio's own code and message (21219 unverified number, 21215 geo
        # permissions) are in the body, which raise_for_status leaves out. The message
        # repeats the To number, so numbers are masked (auth-layer AL15).
        try:
            body = r.json()
            code = body["code"]
            message = re.sub(r"\+\d+", lambda m: mask(m.group()), body["message"])
            log.warning("Twilio %s on %s: %s %s", r.status_code, path, code, message)
        except ValueError, KeyError, TypeError:
            log.warning("Twilio %s on %s", r.status_code, path)
    r.raise_for_status()
    return r
