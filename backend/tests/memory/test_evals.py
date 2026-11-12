"""The eval suite's own deterministic evaluators, with no model (design §9)."""

from types import SimpleNamespace

import evals.summary as ev
from app.seniors.schemas import Citation, FollowUp, SummaryContent, Trend


def run(name: str, output: SummaryContent) -> dict[str, bool]:
    data, expect = next((d, e) for n, d, e in ev.DATA if n == name)
    ctx = SimpleNamespace(inputs=data, output=output, metadata=expect)
    return ev.Deterministic().evaluate(ctx)


def test_dataset_has_every_case():
    assert len(ev.DATASET.cases) == len(ev.DATA) >= 10


def test_good_heater_summary_passes_and_bad_ones_fail():
    data = next(d for n, d, _ in ev.DATA if n == "heater_becomes_follow_up")
    follow_up = FollowUp(
        topic="Calorifer stricat",
        question="S-a reparat caloriferul?",
        call_id=data.call.id,
        quote="Mi s-a stricat caloriferul",
    )
    assert all(run("heater_becomes_follow_up", ev.summary([follow_up])).values())

    wrong_quote = follow_up.model_copy(update={"quote": "Nu am spus asta"})
    assert not run("heater_becomes_follow_up", ev.summary([wrong_quote]))["citations"]

    coded = follow_up.model_copy(update={"question": "Aveți cod roșu?"})
    assert not run("heater_becomes_follow_up", ev.summary([coded]))["no_code_words"]

    assert not run("heater_becomes_follow_up", ev.summary())["topics_present"]


def test_worse_trend_must_cite_the_two_wrong_calls():
    data = next(d for n, d, _ in ev.DATA if n == "two_wrong_days_make_worse_trend")
    w2, w1 = data.earlier
    evidence = [
        Citation(call_id=w1.id, quote="Cred că e duminică"),
        Citation(call_id=w2.id, quote="Joi, mi se pare"),
    ]
    trend = Trend(note="Încurcă zilele.", direction="worse", evidence=evidence)
    assert all(
        run("two_wrong_days_make_worse_trend", ev.summary(trends=[trend])).values()
    )
    steady = trend.model_copy(update={"direction": "steady"})
    assert not run("two_wrong_days_make_worse_trend", ev.summary(trends=[steady]))[
        "worse_trend"
    ]
