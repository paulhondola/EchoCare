"""What one relay session says back (04 §4.3). Today the S1 echo test; the agent loop
that talks to the model is built here (01 §8)."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.voice.models import Speaker, TurnKind

log = logging.getLogger("echocare.voice.agent")

GOODBYE = "Vă mulțumesc. La revedere."


def heard(words: str) -> str:
    return f"Am auzit: {words.rstrip('.!?')}. Mai spuneți ceva?"


Store = Callable[[Speaker, TurnKind, str], Awaitable[None]]


class Relay:
    """The scripted side of one relay session (04 §4.3): what to send back for each
    message from Twilio. Kept apart from the WebSocket, so a script of messages
    tests it with no phone and no database (06 §5)."""

    def __init__(self, greeting: str, store: Store) -> None:
        self.greeting = greeting
        self.store = store

    async def say(self, text: str) -> list[dict[str, Any]]:
        await self.store(Speaker.agent, TurnKind.speech, text)
        return [{"type": "text", "token": text, "last": True}]

    async def handle(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        match message.get("type"):
            case "setup":
                # Twilio speaks the greeting itself, from the TwiML; keep it in the transcript.
                await self.store(Speaker.agent, TurnKind.speech, self.greeting)
                return []
            case "prompt":
                if message.get("last") is False:  # a partial, if ever turned on
                    return []
                words = str(message.get("voicePrompt", "")).strip()
                log.info("heard: %s", words)
                await self.store(Speaker.senior, TurnKind.speech, words)
                return await self.say(heard(words))
            case "dtmf":
                digit = str(message.get("digit", ""))
                log.info("key: %s", digit)
                await self.store(Speaker.senior, TurnKind.keys, digit)
                if digit == "0":
                    return [*await self.say(GOODBYE), {"type": "end"}]
                return await self.say(f"Ați apăsat tasta {digit}.")
            case "interrupt":
                spoken = str(message.get("utteranceUntilInterrupt", ""))
                await self.store(
                    Speaker.system, TurnKind.speech, f"interrupted after: {spoken}"
                )
                return []
            case "error":
                description = str(message.get("description", ""))
                log.warning("relay error: %s", description)
                await self.store(
                    Speaker.system, TurnKind.speech, f"error: {description}"
                )
                return []
            case other:
                log.info("relay: ignored message type %s", other)
                return []
