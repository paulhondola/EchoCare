import uuid
from datetime import date

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.memory.writer import (
    CallFacts,
    SummaryInput,
    citation_errors,
    prompt,
    summary_agent,
)
from app.seniors.schemas import Citation, FollowUp, SummaryContent, Trend


def facts(turns=(), answers=(), call_id=None) -> CallFacts:
    return CallFacts(
        id=call_id or uuid.uuid4(),
        trigger="campaign",
        campaign_kind="wellbeing",
        date=date(2026, 11, 9),
        state="completed",
        final_severity="green",
        final_certainty="high",
        reason=None,
        turns=list(turns),
        answers=list(answers),
    )


def follow_up(call_id: uuid.UUID, quote: str) -> FollowUp:
    return FollowUp(topic="t", question="q?", call_id=call_id, quote=quote)


def content(follow_ups=(), trends=()) -> SummaryContent:
    return SummaryContent(
        follow_ups=list(follow_ups),
        how_to_talk=[],
        trends=list(trends),
        narrative="n",
    )


def data(call: CallFacts, earlier=(), previous=None) -> SummaryInput:
    return SummaryInput(previous=previous, call=call, earlier=list(earlier))


def test_a_quote_from_the_senior_passes():
    call = facts(turns=[("senior", "Nu merge caloriferul de ieri")])
    d = data(call)
    assert (
        citation_errors(d, content([follow_up(call.id, "nu merge caloriferul")])) == []
    )


def test_an_unknown_call_is_refused():
    call = facts(turns=[("senior", "bine")])
    stranger = uuid.uuid4()
    errors = citation_errors(data(call), content([follow_up(stranger, "bine")]))
    assert len(errors) == 1 and str(stranger) in errors[0]


def test_a_quote_from_the_agent_turn_is_refused():
    call = facts(turns=[("agent", "Cum e caloriferul?"), ("senior", "bine")])
    errors = citation_errors(
        data(call), content([follow_up(call.id, "cum e caloriferul")])
    )
    assert (
        len(errors) == 1
        and str(call.id) in errors[0]
        and "caloriferul" not in errors[0]
    )


def test_a_quote_from_a_das_turn_is_refused():
    call = facts(turns=[("das", "Vine ambulanța acum"), ("senior", "bine")])
    errors = citation_errors(
        data(call), content([follow_up(call.id, "vine ambulanța")])
    )
    assert len(errors) == 1


def test_an_answer_quote_is_a_valid_citation():
    call = facts(answers=[("sleep", "bad", True, "am dormit prost")])
    assert (
        citation_errors(data(call), content([follow_up(call.id, "am dormit prost")]))
        == []
    )


def test_a_quote_matches_after_normalization():
    call = facts(turns=[("senior", "Şi iar „nu merge caloriferul”, vai")])
    assert (
        citation_errors(
            data(call), content([follow_up(call.id, "și iar nu merge caloriferul")])
        )
        == []
    )


def test_a_carried_citation_is_trusted():
    old = uuid.uuid4()
    carried = follow_up(old, "cam amețită")
    previous = content([carried])
    d = data(facts(turns=[("senior", "bine")]), previous=previous)
    assert citation_errors(d, content([carried])) == []


def test_a_trend_needs_two_calls():
    call = facts(turns=[("senior", "cam amețită azi"), ("senior", "iar amețită")])
    trend = Trend(
        note="n",
        direction="worse",
        evidence=[
            Citation(call_id=call.id, quote="cam amețită"),
            Citation(call_id=call.id, quote="iar amețită"),
        ],
    )
    errors = citation_errors(data(call), content(trends=[trend]))
    assert len(errors) == 1 and "trends[0]" in errors[0]


@pytest.mark.parametrize("quote", ["", "„”"])
def test_an_empty_quote_is_refused(quote):
    call = facts(turns=[("senior", "bine")])
    errors = citation_errors(data(call), content([follow_up(call.id, quote)]))
    assert len(errors) == 1 and str(call.id) in errors[0]


def test_a_word_fragment_is_refused():
    call = facts(turns=[("senior", "binecuvântat să fie")])
    assert len(citation_errors(data(call), content([follow_up(call.id, "bin")]))) == 1


def test_a_quote_spanning_two_turns_is_refused():
    call = facts(turns=[("senior", "mă doare capul"), ("senior", "și nu dorm")])
    errors = citation_errors(
        data(call), content([follow_up(call.id, "doare capul și nu")])
    )
    assert len(errors) == 1


def test_a_two_call_trend_passes():
    call = facts(turns=[("senior", "cam amețită azi")])
    old = facts(answers=[("sleep", "bad", True, "am dormit prost")])
    trend = Trend(
        note="n",
        direction="worse",
        evidence=[
            Citation(call_id=call.id, quote="cam amețită"),
            Citation(call_id=old.id, quote="am dormit prost"),
        ],
    )
    assert citation_errors(data(call, earlier=[old]), content(trends=[trend])) == []


def test_a_carried_trend_is_trusted():
    trend = Trend(
        note="n",
        direction="steady",
        evidence=[
            Citation(call_id=uuid.uuid4(), quote="x"),
            Citation(call_id=uuid.uuid4(), quote="y"),
        ],
    )
    d = data(facts(turns=[("senior", "bine")]), previous=content(trends=[trend]))
    assert citation_errors(d, content(trends=[trend])) == []


def bad_content_args(call_id: uuid.UUID) -> dict:
    return content([follow_up(call_id, "never said")]).model_dump(mode="json")


async def test_the_agent_retries_then_fails():
    call = facts(turns=[("senior", "bine")])
    d = data(call)
    calls = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, bad_content_args(call.id))]
        )

    agent = summary_agent(FunctionModel(respond))
    with pytest.raises(UnexpectedModelBehavior):
        await agent.run(prompt(d), deps=d)
    assert calls == 3


async def test_the_agent_returns_a_valid_summary():
    call = facts(turns=[("senior", "nu merge caloriferul")])
    d = data(call)
    valid = content([follow_up(call.id, "nu merge caloriferul")])
    agent = summary_agent(TestModel(custom_output_args=valid.model_dump(mode="json")))
    result = await agent.run(prompt(d), deps=d)
    assert result.output == valid


def test_prompt_keeps_romanian_text_and_iso_dates():
    call = facts(turns=[("senior", "Şi cam amețită")])
    text = prompt(data(call))
    assert "amețită" in text and "2026-11-09" in text
