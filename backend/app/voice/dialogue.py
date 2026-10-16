import logging
from collections.abc import Awaitable, Callable
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

from app.voice.models import Speaker, TurnKind

log = logging.getLogger("echocare.voice")

LANGUAGE = "ro-RO"
GOODBYE = "Vă mulțumesc. La revedere."
SORRY = "Ne pare rău, apelul nu poate continua. La revedere."


def greeting(form_of_address: str) -> str:
    """The test call's opening (04 §4.2's greeting, minus the warning and the question)."""
    return (
        f"Bună ziua, {form_of_address}. Sunt asistentul automat al DAS Timișoara. "
        "Acesta este un apel de probă. Nu vă cer niciodată bani sau date. "
        "Spuneți ceva și vă repet ce am auzit. Apăsați zero ca să închideți."
    )


def heard(words: str) -> str:
    return f"Am auzit: {words.rstrip('.!?')}. Mai spuneți ceva?"


def twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(xml, media_type="text/xml")


def sorry() -> Response:
    """A polite Romanian goodbye, never Twilio's own English error (06 §1)."""
    return twiml(f"<Say language={quoteattr(LANGUAGE)}>{escape(SORRY)}</Say><Hangup/>")


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
