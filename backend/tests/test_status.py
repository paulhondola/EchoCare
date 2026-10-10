from datetime import date

import pytest

from app.status import (
    Action,
    Answer,
    CallAnswers,
    Certainty,
    Question,
    Severity,
    final_severity,
    matrix,
    next_code,
    orientation_correct,
)

THURSDAY = date(2026, 10, 8)
SATURDAY = date(2026, 10, 10)


def answers(feeling=("ok", True), orientation=("joi", True), shelter=("yes", True)):
    """A call's answers on THURSDAY; pass None to leave a question unanswered."""
    call = CallAnswers()
    for question, given in (
        (Question.feeling, feeling),
        (Question.orientation, orientation),
        (Question.shelter, shelter),
    ):
        if given is not None:
            value, clear = given
            call.record(question, Answer(value=value, clear=clear, words=value))
    return call


def test_fixed_dates():
    assert THURSDAY.weekday() == 3
    assert SATURDAY.weekday() == 5


def test_orientation():
    assert orientation_correct("joi", THURSDAY)
    assert orientation_correct("Joi", THURSDAY)
    assert orientation_correct("sâmbătă", SATURDAY)
    assert not orientation_correct("luni", THURSDAY)
    assert not orientation_correct("unknown", THURSDAY)


@pytest.mark.parametrize(
    ("call", "severity"),
    [
        (answers(), Severity.green),
        (answers(feeling=("unwell", True)), Severity.yellow),
        (answers(orientation=("luni", True)), Severity.yellow),
        (answers(orientation=("unknown", True)), Severity.yellow),
        (answers(shelter=("no", True)), Severity.yellow),
        (answers(orientation=("luni", True), shelter=("no", True)), Severity.yellow),
        (answers(feeling=("unwell", True), orientation=("luni", True)), Severity.red),
        (answers(feeling=("unwell", True), shelter=("no", True)), Severity.red),
    ],
)
def test_rules_severity(call, severity):
    assert call.severity(THURSDAY) is severity


@pytest.mark.parametrize(
    ("call", "certainty"),
    [
        (answers(), Certainty.high),
        (answers(feeling=("ok", False)), Certainty.medium),
        (answers(feeling=("ok", False), shelter=("yes", False)), Certainty.low),
        (answers(shelter=None), Certainty.medium),  # unanswered counts as unclear
        (CallAnswers(), Certainty.low),
    ],
)
def test_certainty(call, certainty):
    assert call.certainty() is certainty


def test_clear_answer_is_never_overwritten():
    call = answers(feeling=("unwell", True))
    replaced = call.record(
        Question.feeling, Answer(value="ok", clear=True, words="acum mi-e mai bine")
    )
    assert not replaced
    assert call.severity(THURSDAY) is Severity.yellow


def test_unclear_answer_is_overwritten_by_the_reask():
    call = answers(feeling=("ok", False))
    assert call.record(Question.feeling, Answer(value="ok", clear=True, words="bine"))
    assert call.certainty() is Certainty.high


@pytest.mark.parametrize(
    ("severity", "certainty", "action"),
    [
        (Severity.green, Certainty.high, Action(Severity.green, False, False, False)),
        (Severity.green, Certainty.medium, Action(None, False, True, False)),
        (Severity.green, Certainty.low, Action(None, False, True, False)),
        (Severity.yellow, Certainty.high, Action(Severity.yellow, True, False, False)),
        (Severity.yellow, Certainty.medium, Action(Severity.yellow, True, True, False)),
        (Severity.yellow, Certainty.low, Action(Severity.yellow, True, True, False)),
        (Severity.red, Certainty.high, Action(Severity.red, True, False, True)),
        (Severity.red, Certainty.medium, Action(Severity.red, True, False, True)),
        (Severity.red, Certainty.low, Action(Severity.red, True, False, True)),
    ],
)
def test_matrix(severity, certainty, action):
    assert matrix(severity, certainty) == action


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # Tier 1, or tier 2 confirmed or unanswered
        (
            dict(
                starting=Severity.green,
                answered=True,
                certainty=Certainty.high,
                forced_red=True,
            ),
            Severity.red,
        ),
        # Never answered: the starting severity, green becomes yellow
        (dict(starting=Severity.green, answered=False), Severity.yellow),
        (dict(starting=Severity.yellow, answered=False), Severity.yellow),
        # Answered, high: the rules decide, cancelling a watch's yellow (P3)
        (
            dict(
                starting=Severity.yellow,
                answered=True,
                rules=Severity.green,
                certainty=Certainty.high,
            ),
            Severity.green,
        ),
        # Answered, not high: the higher of starting and rules, never green
        (
            dict(
                starting=Severity.green,
                answered=True,
                rules=Severity.green,
                certainty=Certainty.low,
            ),
            Severity.yellow,
        ),
        (
            dict(
                starting=Severity.yellow,
                answered=True,
                rules=Severity.green,
                certainty=Certainty.medium,
            ),
            Severity.yellow,
        ),
        (
            dict(
                starting=Severity.green,
                answered=True,
                rules=Severity.red,
                certainty=Certainty.low,
            ),
            Severity.red,
        ),
        # raise_concern raises, never lowers
        (
            dict(
                starting=Severity.green,
                answered=True,
                rules=Severity.green,
                certainty=Certainty.high,
                concern=Severity.yellow,
            ),
            Severity.yellow,
        ),
        (
            dict(
                starting=Severity.green,
                answered=True,
                rules=Severity.yellow,
                certainty=Certainty.high,
                concern=Severity.red,
            ),
            Severity.red,
        ),
        # Asked for a person or pressed 9: at least yellow
        (
            dict(
                starting=Severity.green,
                answered=True,
                rules=Severity.green,
                certainty=Certainty.high,
                asked_for_person=True,
            ),
            Severity.yellow,
        ),
    ],
)
def test_final_severity(kwargs, expected):
    assert final_severity(**kwargs) is expected


def finish(call, starting=Severity.green, **kwargs):
    return final_severity(
        starting=starting,
        answered=True,
        rules=call.severity(THURSDAY),
        certainty=call.certainty(),
        **kwargs,
    )


def test_worked_examples():
    # 03 §10. 1: all clear and fine
    assert finish(answers()) is Severity.green
    # 2: „cam amețită”, the rest fine
    assert finish(answers(feeling=("unwell", True))) is Severity.yellow
    # 3: vague answers, still vague after the re-ask
    vague = answers(feeling=("ok", False), orientation=("joi", False))
    assert finish(vague) is Severity.yellow
    # 4: unwell, and says „luni” on a Thursday
    assert (
        finish(answers(feeling=("unwell", True), orientation=("luni", True)))
        is Severity.red
    )
    # 6: watch trigger, „am urcat scările, sunt bine”, clear on all three
    assert finish(answers(), starting=Severity.yellow) is Severity.green
    # 8: campaign, two calls not answered
    assert final_severity(starting=Severity.green, answered=False) is Severity.yellow
    # 9: presses 9
    assert finish(answers(), asked_for_person=True) is Severity.yellow
    # 13: fine, then „nu-mi găsesc pastilele de inimă”
    assert finish(answers(), concern=Severity.yellow) is Severity.yellow


def test_next_code():
    # A red with an open or in-progress incident is never lowered (P9).
    assert next_code(Severity.red, True, Severity.green) is Severity.red
    # A resolved red is replaced by the next result.
    assert next_code(Severity.red, False, Severity.green) is Severity.green
    assert next_code(Severity.yellow, False, Severity.green) is Severity.green
    assert next_code(Severity.green, False, Severity.red) is Severity.red
    assert next_code(None, False, Severity.green) is Severity.green
