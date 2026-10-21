"""The relay session scripted, with no phone and no database (06 §5)."""

from app.agent.relay import GOODBYE, Relay
from app.models import Speaker, TurnKind
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
