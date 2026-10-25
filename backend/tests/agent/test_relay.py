"""The relay session scripted, with no phone and no database (06 §5)."""

import json

import pytest

from app.agent.relay import CONNECTING, GOODBYE, Escalation, Relay, heard
from app.models import Speaker, TurnKind
from app.status.alarms import SELF_HARM_HANDOVER
from app.voice.dialogue import greeting


class Transcript:
    def __init__(self):
        self.turns: list[tuple[Speaker, TurnKind, str]] = []

    async def __call__(self, speaker, kind, content):
        self.turns.append((speaker, kind, content))


def text(token: str) -> dict:
    return {"type": "text", "token": token, "last": True}


async def test_a_scripted_session():
    transcript = Transcript()
    relay = Relay(greeting("doamna Maria"), transcript)
    script = [
        ({"type": "setup", "callSid": "CA1", "sessionId": "VX1"}, []),
        (
            {
                "type": "prompt",
                "voicePrompt": "Mă simt bine.",
                "lang": "ro-RO",
                "last": True,
            },
            [text("Am auzit: Mă simt bine. Mai spuneți ceva?")],
        ),
        ({"type": "prompt", "voicePrompt": "Mă", "last": False}, []),
        ({"type": "dtmf", "digit": "5"}, [text("Ați apăsat tasta 5.")]),
        (
            {"type": "interrupt", "utteranceUntilInterrupt": "Ați apăsat"},
            [],
        ),
        ({"type": "error", "description": "Invalid message"}, []),
        ({"type": "something_new"}, []),
        ({"type": "dtmf", "digit": "0"}, [text(GOODBYE), {"type": "end"}]),
    ]
    for message, replies in script:
        assert await relay.handle(message) == replies
    S, K = Speaker, TurnKind
    assert transcript.turns == [
        (S.agent, K.speech, greeting("doamna Maria")),
        (S.senior, K.speech, "Mă simt bine."),
        (S.agent, K.speech, "Am auzit: Mă simt bine. Mai spuneți ceva?"),
        (S.senior, K.keys, "5"),
        (S.agent, K.speech, "Ați apăsat tasta 5."),
        (S.system, K.speech, "interrupted after: Ați apăsat"),
        (S.system, K.speech, "error: Invalid message"),
        (S.senior, K.keys, "0"),
        (S.agent, K.speech, GOODBYE),
    ]


# Hand-over: key 9 or a tier 1 phrase (#48, 04 §4.3, 03 §4).

CALL = "0190a1b2-0000-7000-8000-000000000001"


class HandOver:
    """Records what the session asked for, and answers as the database would."""

    def __init__(self, started: bool = True):
        self.asked: list[tuple[Escalation, str]] = []
        self.started = started

    async def __call__(self, escalation, words):
        self.asked.append((escalation, words))
        return self.started


def end(reason: str) -> dict:
    return {"type": "end", "handoffData": json.dumps({"call": CALL, "reason": reason})}


def prompt(words: str) -> dict:
    return {"type": "prompt", "voicePrompt": words, "last": True}


async def test_key_9_hands_over():
    hand_over = HandOver()
    relay = Relay("Bună ziua.", Transcript(), hand_over, call=CALL)
    replies = await relay.handle({"type": "dtmf", "digit": "9"})
    assert replies == [text(CONNECTING), end("key_9")]
    assert hand_over.asked == [(Escalation.key_9, "")]


async def test_a_tier_1_phrase_hands_over():
    hand_over = HandOver()
    relay = Relay("Bună ziua.", Transcript(), hand_over, call=CALL)
    words = "Am căzut și nu mă pot ridica."
    assert await relay.handle(prompt(words)) == [text(CONNECTING), end("alarm")]
    assert hand_over.asked == [(Escalation.alarm, words)]


async def test_self_harm_speaks_its_own_line():
    relay = Relay("Bună ziua.", Transcript(), HandOver(), call=CALL)
    replies = await relay.handle(prompt("Vreau să mor."))
    assert replies == [text(SELF_HARM_HANDOVER), end("alarm")]


@pytest.mark.parametrize("words", ["Nu am căzut azi.", "Am leșinat puțin ieri."])
async def test_a_negated_or_tier_2_phrase_is_echoed(words):
    hand_over = HandOver()
    relay = Relay("Bună ziua.", Transcript(), hand_over, call=CALL)
    assert await relay.handle(prompt(words)) == [text(heard(words))]
    assert hand_over.asked == []


async def test_a_hand_over_that_does_not_start_says_nothing():
    relay = Relay("Bună ziua.", Transcript(), HandOver(started=False), call=CALL)
    assert await relay.handle({"type": "dtmf", "digit": "9"}) == []


async def test_without_hand_over_key_9_is_echoed():
    relay = Relay("Bună ziua.", Transcript())
    assert await relay.handle({"type": "dtmf", "digit": "9"}) == [
        text("Ați apăsat tasta 9.")
    ]
