"""What one relay session says back (04 §4.3). Today the S1 echo test; the agent loop
that talks to the model is built here (01 §8)."""

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from app.voice.models import Speaker, TurnKind

log = logging.getLogger("echocare.voice.agent")

GOODBYE = "Vă mulțumesc. La revedere."
# Said before the session closes for a hand-over (UC-07 step 3).
CONNECTING = "Vă conectez acum cu un operator, rămâneți pe fir."


class Escalation(StrEnum):
    """Why a call goes to a person (04 §4.3): a tier 1 phrase, or key 9."""

    alarm = "alarm"
    key_9 = "key_9"
    # From the conversation (04 §5): a confirmed tier 2 phrase, a red concern, a red
    # from the rules, or the model asking for a person.
    tier_2 = "tier_2"
    concern = "concern"
    rules = "rules"
    human = "human"


def handoff_reason(e: Escalation) -> str:
    """The reason in the hand-over data (04 §4.4): alarm | key_9 | agent."""
    match e:
        case Escalation.alarm | Escalation.tier_2:
            return "alarm"
        case Escalation.key_9:
            return "key_9"
        case _:
            return "agent"


# Writes the hand-over's report, code and incident, and ends the call `handed_over`;
# whether it started (False once the call is no longer in progress). The router builds
# it, since `agent` reaches no other package's tables.
HandOver = Callable[[Escalation, str], Awaitable[bool]]


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
                words = str(message.get("voicePrompt", "")).strip()
                if message.get("last") is False:
                    # With partial prompts off, only the hang-up sends one: what the
                    # senior was still saying, kept, with nobody left to answer.
                    log.info("unfinished prompt at hang-up, %d chars", len(words))
                    if words:
                        await self.store(Speaker.senior, TurnKind.speech, words)
                    return []
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
