"""What one relay session says back (04 §4.3). Today the S1 echo test; the agent loop
that talks to the model is built here (01 §8)."""

import json
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from app.status.alarms import SELF_HARM_HANDOVER, Tier, check
from app.voice.models import Speaker, TurnKind

log = logging.getLogger("echocare.voice.agent")

GOODBYE = "Vă mulțumesc. La revedere."
# Said before the session closes for a hand-over (UC-07 step 3).
CONNECTING = "Vă conectez acum cu un operator, rămâneți pe fir."


class Escalation(StrEnum):
    """Why a call goes to a person (04 §4.3): a tier 1 phrase, or key 9."""

    alarm = "alarm"
    key_9 = "key_9"


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

    def __init__(
        self,
        greeting: str,
        store: Store,
        hand_over: HandOver | None = None,
        *,
        call: str = "",
    ) -> None:
        self.greeting = greeting
        self.store = store
        # None for a test call, which never hands over (05 §1).
        self.hand_over = hand_over
        self.call = call

    async def say(self, text: str) -> list[dict[str, Any]]:
        await self.store(Speaker.agent, TurnKind.speech, text)
        return [{"type": "text", "token": text, "last": True}]

    async def escalate(
        self, escalation: Escalation, words: str, *, self_harm: bool = False
    ) -> list[dict[str, Any]]:
        """The hand-over (04 §4.4 steps 1 and 2): written first, so a line lost now
        keeps the red; then the last sentence and the end with hand-over data."""
        if not await self.hand_over(escalation, words):
            return []
        data = json.dumps({"call": self.call, "reason": escalation})
        said = await self.say(SELF_HARM_HANDOVER if self_harm else CONNECTING)
        return [*said, {"type": "end", "handoffData": data}]

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
                alarm = check(words)
                # Tier 1 only: tier 2's confirmation belongs to the agent loop (03 §4).
                if self.hand_over and alarm and alarm.tier is Tier.one:
                    return await self.escalate(
                        Escalation.alarm,
                        words,
                        self_harm=alarm.condition == "self_harm",
                    )
                return await self.say(heard(words))
            case "dtmf":
                digit = str(message.get("digit", ""))
                log.info("key: %s", digit)
                await self.store(Speaker.senior, TurnKind.keys, digit)
                if digit == "0":
                    return [*await self.say(GOODBYE), {"type": "end"}]
                if digit == "9" and self.hand_over:
                    return await self.escalate(Escalation.key_9, "")
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
