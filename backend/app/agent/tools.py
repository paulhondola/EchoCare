"""The model's four tools and the server's rules for them (04 §5, 03 §3).

Pure logic, no I/O: the loop stores what an Outcome carries and acts on its hand-over.
Results are English, since the model reads them.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel
from pydantic_ai.tools import ToolDefinition

from app.agent.relay import Escalation
from app.agent.schemas import (
    EndCallArgs,
    RaiseConcernArgs,
    RecordAnswerArgs,
    RequestHumanArgs,
)
from app.status.engine import Answer, CallAnswers, Question, Severity

# Times an unclear answer is asked again before it is kept as it is (design §3).
REASKS = 2

_VALUES = {
    Question.feeling: {"ok", "unwell"},
    Question.shelter: {"yes", "no"},
}


def _tool(name: str, description: str, args: type[BaseModel]) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        parameters_json_schema=args.model_json_schema(),
        # Not sent as strict: PR #62's request to DeepInfra had no `strict` (design §8, 11).
        strict=False,
    )


# The schemas only describe the tools; CallRules checks every argument (design §8).
TOOL_DEFS: list[ToolDefinition] = [
    _tool(
        "record_answer",
        "Record what the senior said about one of the three questions.",
        RecordAnswerArgs,
    ),
    _tool(
        "raise_concern",
        "Something serious outside the three questions. Raises the level, never lowers it.",
        RaiseConcernArgs,
    ),
    _tool(
        "request_human",
        "The senior asked for a person, or the conversation cannot go on.",
        RequestHumanArgs,
    ),
    _tool(
        "end_call",
        "The conversation is finished. Refused until all three answers are recorded.",
        EndCallArgs,
    ),
]


@dataclass
class Outcome:
    result: str  # what the model is told
    hand_over: Escalation | None = None
    reason: str = ""
    answer: tuple[Question, Answer] | None = None  # to store
    concern: tuple[Severity, str] | None = None  # to store
    end: str | None = None  # an accepted summary


def _refused(why: str) -> Outcome:
    return Outcome(f"refused: {why}")


class CallRules:
    def __init__(self, today: date) -> None:
        self.today = today
        self.answers = CallAnswers()
        self.time_up = False
        self._unclear_records: dict[Question, int] = {}

    def pending(self) -> Question | None:
        """An unclear answer that still has a re-ask."""
        for q, a in self.answers.answers.items():
            if not a.clear and self._unclear_records.get(q, 0) <= REASKS:
                return q
        return None

    def missing(self) -> list[Question]:
        return [q for q in Question if q not in self.answers.answers]

    def may_close(self) -> bool:
        return not self.missing() and self.pending() is None

    def run(self, name: str, args: dict[str, Any]) -> Outcome:
        match name:
            case "record_answer":
                return self._record(args)
            case "raise_concern":
                return self._concern(args)
            case "request_human":
                reason = str(args.get("reason") or "")
                return Outcome("ok", hand_over=Escalation.human, reason=reason)
            case "end_call":
                return self._end(args)
            case _:
                return _refused(f"unknown tool {name}")

    def _record(self, args: dict[str, Any]) -> Outcome:
        try:
            question = Question(args.get("field"))
        except ValueError:
            return _refused("field must be feeling, orientation or shelter")
        value, clear = args.get("value"), args.get("clear")
        if not isinstance(clear, bool):
            return _refused("clear must be true or false")
        if not isinstance(value, str) or not value.strip():
            return _refused("value must be a non-empty string")
        if question in _VALUES and value not in _VALUES[question]:
            options = " or ".join(sorted(_VALUES[question]))
            return _refused(f"value for {question} must be {options}")
        answer = Answer(value, clear, str(args.get("words") or ""))
        if not self.answers.record(question, answer):
            return _refused("a clear answer is already recorded")
        result = ""
        if not clear:
            n = self._unclear_records[question] = (
                self._unclear_records.get(question, 0) + 1
            )
            if n <= REASKS:
                result = (
                    f"recorded, but unclear. Ask the {question} question again, "
                    "once, slowly."
                )
        if self.answers.severity(self.today) is Severity.red:
            return Outcome(
                result or "recorded",
                hand_over=Escalation.rules,
                answer=(question, answer),
            )
        if not result:
            left = self.missing()
            result = (
                "recorded. Still to ask: " + ", ".join(left)
                if left
                else "recorded. All questions answered: say a short goodbye and "
                "call end_call."
            )
        return Outcome(result, answer=(question, answer))

    def _concern(self, args: dict[str, Any]) -> Outcome:
        level = args.get("level")
        if level not in ("yellow", "red"):
            return _refused("level must be yellow or red")
        reason = str(args.get("reason") or "")
        return Outcome(
            "recorded",
            hand_over=Escalation.concern if level == "red" else None,
            reason=reason if level == "red" else "",
            # A red one is stored by its hand-over's report, so once (03 §6).
            concern=(Severity.yellow, reason) if level == "yellow" else None,
        )

    def _end(self, args: dict[str, Any]) -> Outcome:
        summary = str(args.get("summary") or "")
        if not self.time_up:
            if self.missing():
                return _refused("still to ask: " + ", ".join(self.missing()))
            if (q := self.pending()) is not None:
                return _refused(f"ask the {q} question again first")
        return Outcome("ok", end=summary)
