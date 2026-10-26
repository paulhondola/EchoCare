"""The pure pieces of the telephony edge: signatures and how callbacks move a call
(#15). The scripted relay session is tests/agent/test_relay.py."""

import uuid
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.settings import get_settings
from app.voice import twilio
from app.voice.calls import CallState, after_callback, answered_by_machine
from app.voice.twilio import (
    dial,
    dial_allowed,
    fetch_call,
    hang_up,
    public_url,
    refused,
    signature,
    signed,
)

C = CallState


def test_signature_matches_twilios_example():
    # Twilio's documented example, also what twilio-python's RequestValidator computes.
    params = {
        "CallSid": "CA1234567890ABCDE",
        "Caller": "+12349013030",
        "Digits": "1234",
        "From": "+12349013030",
        "To": "+18005551212",
    }
    url = "https://mycompany.com/myapp.php?foo=1&bar=2"
    assert signature("12345", url, params.items()) == "0/KCTR6DLpKmkAf8muzZqo1nDgQ="


def test_signed_needs_the_token_and_the_address():
    url = "https://echocare.test/api/voice/status?call=x"
    good = signature("test-auth-token", url, [("CallStatus", "ringing")])
    assert signed(good, [url], [("CallStatus", "ringing")])
    assert not signed(good, [url], [("CallStatus", "completed")])
    assert not signed(good, [url + "y"], [("CallStatus", "ringing")])
    assert not signed("", [url], [("CallStatus", "ringing")])


def test_without_a_token_nothing_is_signed(monkeypatch):
    monkeypatch.setattr(get_settings(), "twilio_auth_token", "")
    url = "https://echocare.test/api/voice/status"
    assert not signed(signature("", url, []), [url], [])


def test_public_url_for_the_websocket():
    assert public_url("/api/voice/relay", "call=1", "wss") == (
        "wss://echocare.test/api/voice/relay?call=1"
    )
    assert public_url("/api/voice/status") == "https://echocare.test/api/voice/status"


@pytest.mark.parametrize(
    ("current", "new", "expected"),
    [
        (C.queued, C.ringing, C.ringing),
        (C.ringing, C.in_progress, C.in_progress),
        (C.in_progress, C.completed, C.completed),
        (C.ringing, C.unanswered, C.unanswered),
        (C.queued, C.failed, C.failed),
        # A lost callback: skip ahead
        (C.queued, C.in_progress, C.in_progress),
        (C.ringing, C.completed, C.completed),
        # Late or repeated: nothing
        (C.in_progress, C.ringing, None),
        (C.completed, C.completed, None),
        (C.unanswered, C.completed, None),
        (C.in_progress, None, None),
        # A machine after pickup (04 §4.2)
        (C.in_progress, C.unanswered, C.unanswered),
        # A state from a newer copy is left alone
        ("on_hold", C.completed, None),
    ],
)
def test_after_callback(current, new, expected):
    assert after_callback(current, new) == expected


@pytest.mark.parametrize(
    ("answered_by", "machine"),
    [
        ("human", False),
        ("unknown", False),
        ("machine_start", True),
        ("machine_end_beep", True),
        ("fax", True),
    ],
)
def test_answered_by_machine(answered_by, machine):
    assert answered_by_machine(answered_by) is machine


@pytest.mark.parametrize(
    ("allowlist", "phone", "allowed"),
    [
        ("", "+40722123456", False),
        ("*", "+40722123456", True),
        ("+40722123456", "+40722123456", True),
        ("+40722123456", "+40722000001", False),
    ],
)
def test_dial_allowed(monkeypatch, allowlist, phone, allowed):
    monkeypatch.setattr(get_settings(), "dial_allowlist", allowlist)
    assert dial_allowed(phone) is allowed


def test_configured_needs_all_three(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", "AC1")
    monkeypatch.setattr(s, "twilio_auth_token", "t")
    monkeypatch.setattr(s, "twilio_from_number", "+1555")
    assert twilio.configured()
    monkeypatch.setattr(s, "twilio_from_number", "")
    assert not twilio.configured()


def test_refused_is_a_4xx_only():
    def status_error(code):
        request = httpx.Request("POST", "https://api.twilio.com/x")
        return httpx.HTTPStatusError(
            "x", request=request, response=httpx.Response(code, request=request)
        )

    assert refused(status_error(400))
    assert not refused(status_error(500))
    assert not refused(httpx.ConnectTimeout("slow"))


@pytest.fixture
def twilio_api(monkeypatch):
    """Twilio's API answered by a mock transport; the requests it saw."""
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", "AC1")
    monkeypatch.setattr(s, "twilio_api_host", "api.dublin.ie1.twilio.com")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"sid": "CA1", "status": "completed", "answered_by": "human"}
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(
        twilio.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


async def test_requests_go_to_the_configured_host(twilio_api):
    call_id = uuid.uuid4()
    assert await dial("+40722123456", call_id, answer="welcome") == "CA1"
    (request,) = twilio_api
    assert str(request.url) == (
        "https://api.dublin.ie1.twilio.com/2010-04-01/Accounts/AC1/Calls.json"
    )
    url = parse_qs(request.content.decode())["Url"][0]
    assert url.endswith(f"/api/voice/welcome?call={call_id}")
    assert parse_qs(request.content.decode())["TimeLimit"] == ["180"]


async def test_hang_up_cancels_a_ringing_call_and_completes_a_live_one(twilio_api):
    await hang_up("CA1", "ringing")
    await hang_up("CA1", "queued")
    await hang_up("CA1", "in-progress")
    await hang_up("CA1")
    sent = [parse_qs(r.content.decode())["Status"][0] for r in twilio_api]
    assert sent == ["canceled", "canceled", "completed", "completed"]
    assert str(twilio_api[0].url).endswith("/Accounts/AC1/Calls/CA1.json")


async def test_fetch_call_reads_the_status_and_who_answered(twilio_api):
    assert await fetch_call("CA1") == ("completed", "human")
    (request,) = twilio_api
    assert request.method == "GET"
    assert str(request.url) == (
        "https://api.dublin.ie1.twilio.com/2010-04-01/Accounts/AC1/Calls/CA1.json"
    )


async def test_an_error_is_logged_without_the_number(monkeypatch, caplog):
    body = {"code": 21211, "message": "The 'To' number +40722123456 is not valid"}
    real = httpx.AsyncClient
    monkeypatch.setattr(
        twilio.httpx,
        "AsyncClient",
        lambda **kw: real(
            transport=httpx.MockTransport(lambda r: httpx.Response(400, json=body)),
            **kw,
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await dial("+40722123456", uuid.uuid4())
    assert "+40722***456" in caplog.text and "21211" in caplog.text
    assert "+40722123456" not in caplog.text
