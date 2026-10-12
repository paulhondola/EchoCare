"""Talking to Twilio: request signatures (01 §4, channels 6 and 7) and the Voice API
(channel 5, 04 §4.1).

No Twilio library: its client blocks, and everything in the request path is
asynchronous (01 §8). The Voice API is two form posts through httpx, and the signature
is Twilio's documented HMAC, a few lines here.
"""

import base64
import hashlib
import hmac
import uuid
from collections.abc import Iterable

import httpx

from app.settings import get_settings

API = "https://api.twilio.com/2010-04-01"

# How long the senior's phone rings before Twilio gives up (04 §4.1).
RING_SECONDS = 30


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
    """The address Twilio called, rebuilt from PUBLIC_BASE_URL: behind Railway's proxy
    or the ngrok tunnel, the request's own URL is not the one Twilio signed."""
    base = get_settings().public_base_url.rstrip("/")
    if scheme is not None:
        base = scheme + base[base.index(":") :]
    return base + path + (f"?{query}" if query else "")


def voice_url(path: str, call_id: uuid.UUID, scheme: str | None = None) -> str:
    """A callback address carrying our call id (04 §4.1)."""
    return public_url(f"/api/voice/{path}", f"call={call_id}", scheme)


async def dial(to: str, call_id: uuid.UUID) -> str:
    """Asks Twilio to place the call (04 §4.1); Twilio's call id. Raises httpx.HTTPError
    when Twilio refuses or cannot be reached."""
    s = get_settings()
    data = {
        "To": to,
        "From": s.twilio_from_number,
        "Url": voice_url("answer", call_id),
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
    }
    r = await _post("Calls.json", data)
    return r.json()["sid"]


async def hang_up(twilio_call_id: str) -> None:
    """Ends a live call, as when a machine answered (04 §4.2)."""
    await _post(f"Calls/{twilio_call_id}.json", {"Status": "completed"})


async def _post(path: str, data: dict) -> httpx.Response:
    s = get_settings()
    async with httpx.AsyncClient(
        auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=10
    ) as client:
        r = await client.post(
            f"{API}/Accounts/{s.twilio_account_sid}/{path}", data=data
        )
    r.raise_for_status()
    return r
