"""The model seam on Pydantic AI's FunctionModel, never the network (04 §5, design §8)."""

from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.agent.model import SETTINGS, ToolCall, stream_with

MESSAGES = [ModelRequest([UserPromptPart("bine")])]


async def items(stream_function):
    stream = stream_with(FunctionModel(stream_function=stream_function))
    return [i async for i in stream(MESSAGES)]


async def test_settings_reach_the_model():
    seen: list[AgentInfo] = []

    async def fn(messages, info):
        seen.append(info)
        yield "Bună ziua."

    await items(fn)
    assert (
        seen[0].model_settings
        == SETTINGS
        == {
            "temperature": 0.3,
            "max_tokens": 1000,
            "extra_body": {"reasoning_effort": "none"},
        }
    )
    assert [t.name for t in seen[0].function_tools] == [
        "record_answer",
        "raise_concern",
        "request_human",
        "end_call",
    ]


async def test_text_streams_as_pieces():
    async def fn(messages, info):
        yield "Bună "
        yield "ziua"

    assert [i for i in await items(fn) if i] == ["Bună ", "ziua"]


async def test_tool_call_pieces_yield_liveness():
    async def fn(messages, info):
        yield {0: DeltaToolCall("record_answer", '{"field": "fee', tool_call_id="c1")}
        yield {0: DeltaToolCall(None, 'ling", "value": "ok", "clear": true}')}
        yield {1: DeltaToolCall("end_call", '{"summary": "s"}', tool_call_id="c2")}

    got = await items(fn)
    calls = [i for i in got if isinstance(i, ToolCall)]
    # Every tool-call piece yields "" first, so the loop's timeout sees the stream alive.
    assert got[: got.index(calls[0])].count("") >= 3
    assert calls == [
        ToolCall(
            "c1", "record_answer", {"field": "feeling", "value": "ok", "clear": True}
        ),
        ToolCall("c2", "end_call", {"summary": "s"}),
    ]


async def test_bad_tool_arguments_become_empty():
    async def fn(messages, info):
        yield {
            0: DeltaToolCall("record_answer", '{"field": "feeling"', tool_call_id="c1")
        }
        yield {1: DeltaToolCall("end_call", "[1]", tool_call_id="c2")}

    calls = [i for i in await items(fn) if isinstance(i, ToolCall)]
    assert calls == [
        ToolCall("c1", "record_answer", {}),
        ToolCall("c2", "end_call", {}),
    ]


async def test_closing_early_closes_the_stream():
    closed = []

    async def fn(messages, info):
        try:
            yield "Vă "
            yield "simțiți?"
        finally:
            closed.append(True)

    stream = aiter(stream_with(FunctionModel(stream_function=fn))(MESSAGES))
    assert await anext(stream) == "Vă "
    await stream.aclose()
    assert closed == [True]
