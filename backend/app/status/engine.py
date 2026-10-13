"""Status engine (03 §3, §5, §6, G10).

The model converses and records answers; these fixed rules decide severity, certainty and
the action. Nothing here touches the database, so it is tested without one (06 §5).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum, StrEnum
from zoneinfo import ZoneInfo

from app.status.alarms import normalize

BUCHAREST = ZoneInfo("Europe/Bucharest")


class Severity(IntEnum):
    # Ordered, so max() gives the higher level: the model can raise it, never lower it.
    green = 0
    yellow = 1
    red = 2


class Certainty(IntEnum):
    low = 0
    medium = 1
    high = 2


class Question(StrEnum):
    feeling = "feeling"
    orientation = "orientation"
    shelter = "shelter"


@dataclass(frozen=True)
class Answer:
    # feeling: ok | unwell; orientation: the named day or unknown; shelter: yes | no (03 §3).
    value: str
    clear: bool
    words: str


# Monday first, matching date.weekday().
WEEKDAYS = ("luni", "marti", "miercuri", "joi", "vineri", "sambata", "duminica")


def today_in_bucharest() -> date:
    return datetime.now(BUCHAREST).date()


def orientation_correct(named_day: str, today: date) -> bool:
    """The server, not the model, checks the day (03 §3). Unknown or another day is wrong."""
    return normalize(named_day) == WEEKDAYS[today.weekday()]


@dataclass
class CallAnswers:
    """The answers recorded during one call, with the overwrite rule applied."""

    answers: dict[Question, Answer] = field(default_factory=dict)

    def record(self, question: Question, answer: Answer) -> bool:
        """Store an answer. Only an unclear earlier answer may be replaced (03 §3).

        Returns False when the earlier answer was clear and is kept, so a clear
        „cam amețită” is never replaced by a later „acum mi-e mai bine”.
        """
        earlier = self.answers.get(question)
        if earlier is not None and earlier.clear:
            return False
        self.answers[question] = answer
        return True

    def worrying(self, question: Question, today: date) -> bool:
        answer = self.answers.get(question)
        if answer is None:
            return False
        match question:
            case Question.feeling:
                return answer.value == "unwell"
            case Question.orientation:
                return not orientation_correct(answer.value, today)
            case Question.shelter:
                return answer.value == "no"

    def severity(self, today: date) -> Severity:
        """The rules' severity (03 §3, v3 §9.2)."""
        unwell = self.worrying(Question.feeling, today)
        wrong_day = self.worrying(Question.orientation, today)
        no_shelter = self.worrying(Question.shelter, today)
        if unwell and (wrong_day or no_shelter):
            return Severity.red
        if unwell or wrong_day or no_shelter:
            return Severity.yellow
        return Severity.green

    def unclear(self) -> list[Question]:
        # A question not yet answered counts as unclear: unclear never counts as fine (03 §5).
        return [
            q for q in Question if (a := self.answers.get(q)) is None or not a.clear
        ]

    def certainty(self) -> Certainty:
        match len(self.unclear()):
            case 0:
                return Certainty.high
            case 1:
                return Certainty.medium
            case _:
                return Certainty.low


@dataclass(frozen=True)
class Action:
    """One cell of the matrix (03 §5)."""

    # The code to set now, or None to leave it until the retry settles it.
    code: Severity | None
    alert: bool
    retry: bool
    hand_over: bool


def matrix(severity: Severity, certainty: Certainty) -> Action:
    if severity is Severity.red:
        # The red row ignores certainty by design.
        return Action(code=Severity.red, alert=True, retry=False, hand_over=True)
    if severity is Severity.yellow:
        return Action(
            code=Severity.yellow,
            alert=True,
            retry=certainty is not Certainty.high,
            hand_over=False,
        )
    if certainty is Certainty.high:
        return Action(code=Severity.green, alert=False, retry=False, hand_over=False)
    # An uncertain green retries once; if still not high, final_severity makes it yellow.
    return Action(code=None, alert=False, retry=True, hand_over=False)


def final_severity(
    *,
    starting: Severity,
    answered: bool,
    rules: Severity = Severity.green,
    certainty: Certainty = Certainty.low,
    forced_red: bool = False,
    concern: Severity | None = None,
    asked_for_person: bool = False,
) -> Severity:
    """Combine the sources once the call ends or goes unanswered for the last time (03 §6).

    forced_red: a tier 1 phrase, or a tier 2 phrase confirmed or left unanswered.
    A dropped call or an early hang-up is passed as answered with low certainty.
    Not for welcome calls, which never change the code.
    """
    if forced_red:
        return Severity.red
    if not answered:
        result = starting
    elif certainty is Certainty.high:
        # P3: a clear green cancels a watch trigger's starting yellow.
        result = rules
    else:
        result = max(starting, rules)
    if result is Severity.green and not (answered and certainty is Certainty.high):
        result = Severity.yellow
    if concern is not None:
        result = max(result, concern)
    if asked_for_person:
        result = max(result, Severity.yellow)
    return result


def next_code(
    current: Severity | None, incident_unresolved: bool, result: Severity
) -> Severity:
    """The senior's code after a call's result (03 §8, P9).

    A red is never lowered while its incident is open or in progress. A resolved red, a
    yellow or a green is replaced by the next result.
    """
    if current is Severity.red and incident_unresolved:
        return Severity.red
    return result
