"""The pure pieces of the telephony edge: signatures and how callbacks move a call
(#15). The scripted relay session is tests/agent/test_relay.py."""

import pytest

from app.core.settings import get_settings
from app.voice.calls import CallState, after_callback, answered_by_machine
from app.voice.twilio import public_url, signature, signed

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
