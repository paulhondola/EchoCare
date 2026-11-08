"""The agent's side of one wellbeing call (04 §4.3, 04 §5, design §4, §5): alarm phrases
before the model, the model's turns streamed back as text, the server rules on its tool
calls, and the call's end or hand-over.

Pure asyncio with injected callables, so a script of messages tests it with no phone,
no model and no database (06 §5). A turn runs as its own task, so `interrupt`, key 9 or
a hang-up acts at once (design §4, Concurrency).
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import aclosing
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.agent.model import ModelStream, ToolCall
from app.agent.prompt import instructions
from app.agent.relay import CONNECTING, Escalation, HandOver, Store, handoff_reason
from app.agent.tools import CallRules, Outcome
from app.status.alarms import (
    SELF_HARM_HANDOVER,
    Tier,
    check,
    confirmation_question,
    needs_help,
)
from app.status.engine import Answer, Question, Severity, today_in_bucharest
from app.voice.models import Speaker, TurnKind

log = logging.getLogger("echocare.voice.agent")

FAILURE = "Ne pare rău, avem o problemă tehnică și trebuie să închidem. La revedere."
# Said when a turn's last round still has no text, to keep the line alive (design §4).
STALL = "Vă mulțumesc."
TIME_UP = "Vă mulțumesc pentru timpul acordat. La revedere."
DEFAULT_SUMMARY = "Convorbire cu asistentul."
DROPPED_SUMMARY = "Convorbirea s-a întrerupt."
TIME_UP_SUMMARY = "Limita de timp a apelului."

Send = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class Line:
    """What the agent writes, all through `voice` (ADR-005)."""

    store: Store
    answer: Callable[[Question, Answer], Awaitable[None]]
    concern: Callable[[Severity, str], Awaitable[None]]
    hand_over: HandOver
    end: Callable[[str, bool], Awaitable[None]]  # (summary, dropped)


@dataclass(frozen=True)
class Limits:
    # Model failure without a first item, or a stream that goes quiet that long (design §4).
    first_token: float = 10.0
    call_limit: float = 180.0  # from setup (design §5)
    tier2_wait: float = 8.0  # for the confirmation's reply, once it is spoken (03 §4)
    # ponytail: an estimate of the voice's pace; Twilio reports no end of speech.
    seconds_per_word: float = 0.5
    rounds: int = 3  # model calls per turn (design §4)


LIMITS = Limits()


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and (e := task.exception()):
        log.error("agent task failed", exc_info=e)


def _assistant(text: str, calls: list[ToolCall]) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": json.dumps(c.arguments, ensure_ascii=False),
                },
            }
            for c in calls
        ]
    return message


class Agent:
    def __init__(
        self,
        *,
        call: str,
        greeting: str,
        form_of_address: str,
        heat: bool,
        follow_up: str | None = None,
        how_to_talk: tuple[str, ...] = (),
        send: Send,
        line: Line,
        model: ModelStream,
        today: date | None = None,
        limits: Limits = LIMITS,
    ) -> None:
        self.call = call
        self.greeting = greeting
        self._send_raw = send
        self.line = line
        self.model = model
        self.limits = limits
        self.rules = CallRules(today or today_in_bucharest())
        # The greeting is the conversation's first agent turn (design §4, Call context).
        self.history: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": instructions(form_of_address, heat, follow_up, how_to_talk),
            },
            {"role": "assistant", "content": greeting},
        ]
        # The history index of the model's last spoken text, which an interrupt cuts
        # down to what was heard; None while the current turn has spoken nothing yet.
        self._spoken: int | None = 1
        self._summary: str | None = None
        self._pending: str | None = None  # the tier 2 sentence awaiting its reply
        self._turn: asyncio.Task | None = None
        self._limit: asyncio.Task | None = None
        self._confirm: asyncio.Task | None = None
        # A round's transcript, answer and concern writes, which outlive a cancel.
        self._writes: set[asyncio.Task] = set()
        # Set by the one path that ends the call (hand-over, end, failure, time-up or
        # close); after it nothing starts or cancels anything else.
        self._ending = False
        # True once `end` was sent, or the line closed: nothing is sent after it.
        self.finished = False

    # Messages from Twilio (04 §4.3).

    async def handle(self, message: dict[str, Any]) -> None:
        match message.get("type"):
            case "setup":
                if self._limit is not None:
                    log.warning("relay: a second setup, call %s", self.call)
                    return
                # Twilio speaks the greeting itself, from the TwiML.
                await self._store(Speaker.agent, TurnKind.speech, self.greeting)
                self._limit = self._spawn(self._time_up())
            case "prompt":
                words = str(message.get("voicePrompt", "")).strip()
                if message.get("last") is False:
                    # Only the hang-up sends one: kept, with nobody left to answer.
                    if words:
                        await self._store(Speaker.senior, TurnKind.speech, words)
                        # A tier 1 phrase is still red, said as the line drops (03 §4).
                        alarm = check(words)
                        if alarm and alarm.tier is Tier.one:
                            self.finished = True  # nobody is left to hear a reply
                            await self._hand_over(Escalation.alarm, words)
                    return
                # Never the words: senior speech is health data.
                log.info("heard %d chars, call %s", len(words), self.call)
                await self._store(Speaker.senior, TurnKind.speech, words)
                if not self._ending:
                    await self._prompt(words)
            case "dtmf":
                digit = str(message.get("digit", ""))
                log.info("key: %s", digit)
                await self._store(Speaker.senior, TurnKind.keys, digit)
                if not self._ending:
                    await self._key(digit)
            case "interrupt":
                spoken = str(message.get("utteranceUntilInterrupt", ""))
                # A confirmation question is not in the history (03 §4).
                if not self._ending and self._pending is None:
                    await self._cancel(self._turn)
                    self._heard(spoken)
                await self._store(
                    Speaker.system, TurnKind.speech, f"interrupted after: {spoken}"
                )
            case "error":
                description = str(message.get("description", ""))
                log.warning("relay error: %s", description)
                await self._store(
                    Speaker.system, TurnKind.speech, f"error: {description}"
                )
            case other:
                log.info("relay: ignored message type %s", other)

    async def close(self) -> None:
        """The line is gone. A pending confirmation is red (03 §4): it hands over, which
        does nothing once the call is no longer in progress. An end or hand-over already
        under way finishes its writes; anything else is cancelled."""
        self.finished = True
        if self._pending is not None:
            await self._hand_over(Escalation.tier_2, self._pending)
        elif self._claim():
            await self._stop_others()
            # A hang-up during the goodbye: the rules already close it (03 §9).
            if self.rules.may_close():
                await self._try(self.line.end(self._summary or DEFAULT_SUMMARY, False))
        tasks = (self._turn, self._limit, self._confirm, *self._writes)
        if live := [t for t in tasks if t]:
            await asyncio.wait(live)

    async def idle(self) -> None:
        """Waits for the running turn, for tests."""
        if self._turn is not None:
            await asyncio.wait([self._turn])

    # Alarm phrases and keys, before and without the model (03 §4).

    async def _prompt(self, words: str) -> None:
        if (sentence := self._pending) is not None:
            await self._cancel(self._confirm)
            self._pending = None
            if needs_help(words):
                await self._hand_over(Escalation.tier_2, sentence)
                return
            # The reply is checked like any sentence before the model sees it.
            alarm = check(words)
            if alarm and alarm.tier is Tier.one:
                await self._alarm(words, alarm.condition)
                return
            await self._declined(sentence, words)
            return
        alarm = check(words)
        if alarm and alarm.tier is Tier.one:
            await self._alarm(words, alarm.condition)
        elif alarm:
            await self._cancel(self._turn)
            if self._ending:  # the cancelled turn handed over (03 §6)
                return
            # Pending before it is said, so a hang-up during the question is red too.
            self._pending = words
            question = confirmation_question(words)
            await self._say(question)
            if not self._ending:
                speaking = len(question.split()) * self.limits.seconds_per_word
                self._confirm = self._spawn(self._confirm_wait(speaking))
        else:
            await self._start_turn([words])

    async def _key(self, digit: str) -> None:
        if digit == "9":
            await self._hand_over(Escalation.key_9, "")
        elif (sentence := self._pending) is not None and digit in ("1", "2"):
            await self._cancel(self._confirm)
            self._pending = None
            if digit == "1":
                await self._hand_over(Escalation.tier_2, sentence)
            else:
                await self._declined(sentence, f"(tasta {digit})")

    async def _alarm(self, words: str, condition: str) -> None:
        said = SELF_HARM_HANDOVER if condition == "self_harm" else CONNECTING
        await self._hand_over(Escalation.alarm, words, said)

    async def _declined(self, sentence: str, reply: str) -> None:
        """A clear no to the confirmation: both go to the model as ordinary turns,
        and the transcript keeps the match for review (design §5)."""
        await self._store(Speaker.system, TurnKind.speech, "Confirmare nivel 2: nu")
        await self._start_turn([sentence, reply])

    async def _confirm_wait(self, speaking: float) -> None:
        # The wait starts once the question has been heard, not when it is sent.
        await asyncio.sleep(speaking + self.limits.tier2_wait)
        # Silence is red (03 §4).
        await self._hand_over(Escalation.tier_2, self._pending or "")

    # A turn (design §4).

    async def _start_turn(self, said: list[str]) -> None:
        if self._ending:  # the call ended during an await before this
            return
        await self._cancel(self._turn)
        if self._ending:  # the cancelled turn handed over (03 §6)
            return
        self.history.extend({"role": "user", "content": w} for w in said)
        self._spoken = None
        self._turn = self._spawn(self._run_turn())

    async def _run_turn(self) -> None:
        text = ""
        for n in range(1, self.limits.rounds + 1):
            try:
                text, calls, json_like = await self._round()
            except Exception:  # a provider error or no first item in time
                log.exception("model round failed, call %s", self.call)
                await self._finish(DROPPED_SUMMARY, dropped=True, said=FAILURE)
                return
            outcomes = [self.rules.run(c.name, c.arguments) for c in calls]
            # The whole round at once, so a cancel never leaves tool calls without
            # their results for the next request.
            if text:
                self._spoken = len(self.history)
            if text or calls:
                self.history.append(_assistant(text, calls))
            self.history.extend(
                {"role": "tool", "tool_call_id": c.id, "content": o.result}
                for c, o in zip(calls, outcomes, strict=True)
            )
            for o in outcomes:
                if o.end is not None:
                    self._summary = o.end
            red = next((o for o in outcomes if o.hand_over), None)
            # Shielded and kept: an interrupt or hang-up must not lose what was said,
            # and nothing ends the call before it lands.
            write = self._spawn(self._keep(text, outcomes))
            self._writes.add(write)
            write.add_done_callback(self._writes.discard)
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                # Red acts at once (03 §6): an interrupt or a new prompt must not lose
                # the round's hand-over. It is claimed now, so nothing else starts; it
                # becomes the turn, so `idle` and `close` wait for it, and it waits for
                # the write before `line.hand_over`.
                if red and self._claim():
                    self._turn = self._spawn(
                        self._handing_over(red.hand_over, red.reason)
                    )
                raise
            if red:
                await self._hand_over(red.hand_over, red.reason)
                return
            # A goodbye with a refused end_call goes round again, so the model hears
            # the refusal instead of leaving the line silent.
            refused_end = any(
                c.name == "end_call" and o.end is None
                for c, o in zip(calls, outcomes, strict=True)
            )
            # A JSON-looking round is probably a tool call written as text: ask again.
            if (text and not refused_end) or (not calls and not json_like):
                break
        else:  # the last round still had no text
            await self._say(STALL)
        if self._summary is not None or self.rules.may_close():
            await self._finish(self._summary or DEFAULT_SUMMARY)

    async def _round(self) -> tuple[str, list[ToolCall], bool]:
        """One model call: text pieces sent as they come, the latest held back so the
        last goes out with `last: true`. Returns (spoken text, tool calls, json_like)."""
        calls: list[ToolCall] = []
        pieces: list[str] = []
        held: str | None = None
        json_like: bool | None = None
        stream = aiter(self.model(list(self.history)))
        async with aclosing(stream):
            while True:
                # Every chunk, tool-call pieces included, comes in time (design §4).
                async with asyncio.timeout(self.limits.first_token):
                    item = await anext(stream, None)
                if item is None:
                    break
                if isinstance(item, ToolCall):
                    calls.append(item)
                elif item:
                    pieces.append(item)
                    if json_like is None and (start := "".join(pieces).lstrip()):
                        # Unsafe text guard (design §4).
                        json_like = start.startswith("{")
                        item = "".join(pieces)
                    if json_like is False:
                        if held is not None:
                            await self._send(_text(held, last=False))
                        held = item
        if held is not None:
            await self._send(_text(held, last=True))
        if json_like:
            log.warning(
                "model text looks like JSON, not sent: %d chars, call %s",
                len("".join(pieces)),
                self.call,
            )
            return "", calls, True
        return "".join(pieces).strip(), calls, False

    async def _keep(self, text: str, outcomes: list[Outcome]) -> None:
        if text:
            await self._store(Speaker.agent, TurnKind.speech, text)
        for o in outcomes:
            if o.answer:
                await self._try(self.line.answer(*o.answer))
            if o.concern:
                await self._try(self.line.concern(*o.concern))

    async def _try(self, write: Awaitable[None]) -> None:
        """A failed write is logged and the round goes on: its hand-over or close comes
        from CallRules in memory, and the senior is never left in silence (design §5)."""
        try:
            await write
        except Exception as e:  # noqa: BLE001 - logged below, without the words
            # Type only: the error can carry the senior's words or the values.
            log.error("write failed, call %s: %s", self.call, type(e).__name__)

    # Ending the call: exactly one path does it.

    async def _time_up(self) -> None:
        await asyncio.sleep(self.limits.call_limit)
        self.rules.time_up = True
        if self._pending is not None:  # an unanswered confirmation is red (03 §4)
            await self._hand_over(Escalation.tier_2, self._pending)
        elif self.rules.answers.severity(self.rules.today) is Severity.red:
            # A red round whose write was still landing: it hands over (03 §6).
            await self._hand_over(Escalation.rules, "")
        else:
            await self._finish(TIME_UP_SUMMARY, said=TIME_UP)

    async def _hand_over(
        self, escalation: Escalation, reason: str, said: str = CONNECTING
    ) -> None:
        if self._claim():
            await self._handing_over(escalation, reason, said)

    async def _handing_over(
        self, escalation: Escalation, reason: str, said: str = CONNECTING
    ) -> None:
        """Once claimed. Written first, so a line lost now keeps the red; then the last
        sentence and the end with hand-over data (04 §4.4)."""
        try:
            await self._stop_others()
            try:
                started = await self.line.hand_over(escalation, reason)
            except Exception as e:  # noqa: BLE001 - logged below, without the words
                # Type only: the error can carry the reason, the senior's words.
                log.error("hand-over failed, call %s: %s", self.call, type(e).__name__)
                started = True  # Twilio's action URL still routes the call to a person
            if started:
                data = json.dumps(
                    {"call": self.call, "reason": handoff_reason(escalation)}
                )
                await self._say(said)
                await self._send({"type": "end", "handoffData": data})
        finally:
            self.finished = True

    async def _finish(
        self, summary: str, *, dropped: bool = False, said: str | None = None
    ) -> None:
        if not self._claim():
            return
        await self._stop_others()
        if said:
            await self._say(said)
        try:
            await self.line.end(summary, dropped)
        finally:  # never leave the senior on an open line
            await self._send({"type": "end"})
            self.finished = True

    def _claim(self) -> bool:
        if self._ending:
            return False
        self._ending = True
        return True

    # Plumbing.

    async def _send(self, message: dict[str, Any]) -> None:
        if not self.finished:
            await self._send_raw(message)

    async def _say(self, text: str) -> None:
        if not self.finished:  # unheard words are not the transcript's
            await self._send(_text(text, last=True))
            await self._store(Speaker.agent, TurnKind.speech, text)

    async def _store(self, speaker: Speaker, kind: TurnKind, text: str) -> None:
        """A transcript row that may fail: an alarm, a hand-over or an end never waits
        on the transcript (design §5)."""
        await self._try(self.line.store(speaker, kind, text))

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task:
        task = asyncio.create_task(coro)
        task.add_done_callback(_log_failure)
        return task

    async def _cancel(self, task: asyncio.Task | None) -> None:
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        await asyncio.wait([task])

    async def _stop_others(self) -> None:
        for task in (self._turn, self._limit, self._confirm):
            await self._cancel(task)
        if self._writes:  # their failures are logged by _spawn's callback
            await asyncio.wait(set(self._writes))

    def _heard(self, spoken: str) -> None:
        """Keep only what the senior heard of the model's last text (design §4)."""
        if self._spoken is None:  # cut mid-stream, or the stall line
            if spoken:
                self.history.append({"role": "assistant", "content": spoken})
            return
        message = self.history[self._spoken]
        message["content"] = spoken or None
        if not spoken and "tool_calls" not in message:
            del self.history[self._spoken]
            self._spoken = None


def _text(token: str, *, last: bool) -> dict[str, Any]:
    return {"type": "text", "token": token, "last": last}
