from datetime import date

import pytest

from app.agent.prompt import instructions
from app.agent.relay import Escalation, handoff_reason
from app.agent.tools import CallRules, Outcome
from app.status.engine import Question, Severity


def rules() -> CallRules:
    return CallRules(date(2026, 11, 8))  # a Sunday


def rec(r: CallRules, field: str, value: str, clear: bool) -> Outcome:
    return r.run(
        "record_answer",
        {"field": field, "value": value, "clear": clear, "words": "x"},
    )


def test_a_clear_answer_is_never_overwritten():
    r = rules()
    rec(r, "feeling", "unwell", True)
    out = rec(r, "feeling", "ok", True)
    assert out.answer is None and "already recorded" in out.result
    assert r.answers.answers[Question.feeling].value == "unwell"


def test_an_unclear_answer_is_asked_again_twice_then_kept():
    r = rules()
    for _ in range(2):
        assert "feeling" in rec(r, "feeling", "ok", False).result
        assert r.pending() is Question.feeling
    third = rec(r, "feeling", "ok", False)
    assert r.pending() is None and "again" not in third.result


def test_end_call_waits_for_all_three_and_the_re_asks():
    r = rules()
    assert r.run("end_call", {"summary": "s"}).end is None
    rec(r, "feeling", "ok", False)
    rec(r, "orientation", "duminică", True)
    rec(r, "shelter", "yes", True)
    refused = r.run("end_call", {"summary": "s"})
    assert refused.end is None and "feeling" in refused.result
    rec(r, "feeling", "ok", True)
    assert r.may_close() and r.run("end_call", {"summary": "s"}).end == "s"


def test_end_call_is_accepted_at_the_time_limit():
    r = rules()
    r.time_up = True
    assert r.run("end_call", {"summary": "s"}).end == "s"


def test_unwell_and_a_wrong_day_hands_over_at_once():
    r = rules()
    rec(r, "feeling", "unwell", True)
    assert rec(r, "orientation", "marți", True).hand_over is Escalation.rules


def test_a_red_concern_hands_over_and_a_yellow_one_is_only_stored():
    r = rules()
    y = r.run("raise_concern", {"level": "yellow", "reason": "pastile", "words": "w"})
    assert (y.concern, y.hand_over) == ((Severity.yellow, "pastile"), None)
    red = r.run("raise_concern", {"level": "red", "reason": "r", "words": "w"})
    assert red.hand_over is Escalation.concern and red.reason == "r"


def test_request_human_hands_over():
    out = rules().run("request_human", {"reason": "nu aude"})
    assert (out.hand_over, out.reason) == (Escalation.human, "nu aude")


def test_a_record_with_missing_arguments_is_refused():
    out = rules().run("record_answer", {})
    assert out.answer is None and out.result.startswith("refused")


@pytest.mark.parametrize(
    "field,value", [("feeling", "fine"), ("shelter", "maybe"), ("mood", "ok")]
)
def test_values_outside_the_spec_are_refused(field, value):
    assert rec(rules(), field, value, True).answer is None


def test_an_unknown_tool_is_refused():
    assert rules().run("send_sms", {}).result.startswith("refused")


def test_handoff_reasons():
    assert [handoff_reason(e) for e in Escalation] == [
        "alarm",
        "key_9",
        "alarm",
        "agent",
        "agent",
        "agent",
    ]


def test_the_instructions_name_the_shelter_and_the_new_limits():
    cold, heat = instructions("doamna Elena", False), instructions("doamna Elena", True)
    assert "doamna Elena" in cold and "warm place" in cold and "cool place" in heat
    # A watch or manual call has no warning; the greeting says why we call (I4).
    assert "warning" not in cold and "warning" not in heat
    assert "never say you have notified" in cold.lower()
    assert "never give yourself a name" in cold.lower()


def test_a_request_human_reason_is_a_string():
    outcome = rules().run("request_human", {"reason": 5})
    assert outcome.reason == "5"
