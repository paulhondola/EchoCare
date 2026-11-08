"""The DeepInfra stream against a fake client, never the network (04 §5)."""

from types import SimpleNamespace as NS

from app.agent.model import ToolCall, deepinfra
from app.agent.tools import TOOLS


def text_chunk(text):
    return NS(choices=[NS(delta=NS(content=text, tool_calls=None), finish_reason=None)])


def tool_chunk(index, id=None, name=None, args=None, finish=None):
    call = NS(index=index, id=id, function=NS(name=name, arguments=args))
    return NS(
        choices=[NS(delta=NS(content=None, tool_calls=[call]), finish_reason=finish)]
    )


class FakeClient:
    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs = {}
        self.chat = NS(completions=NS(create=self.create))

    async def create(self, **kwargs):
        self.kwargs = kwargs

        async def gen():
            for chunk in self.chunks:
                yield chunk

        return gen()


async def test_text_streams_in_order_and_the_request_is_exact():
    client = FakeClient([text_chunk("Bună "), text_chunk("ziua")])
    items = [
        i
        async for i in deepinfra("k", "m", client=client)(
            [{"role": "user", "content": "x"}]
        )
    ]
    assert items == ["Bună ", "ziua"]
    kw = client.kwargs
    assert (kw["model"], kw["stream"], kw["temperature"], kw["max_tokens"]) == (
        "m",
        True,
        0.3,
        1000,
    )
    assert kw["extra_body"] == {"reasoning_effort": "none"} and kw["tools"] is TOOLS


async def test_tool_call_pieces_are_joined_after_the_text():
    client = FakeClient(
        [
            tool_chunk(0, id="c1", name="record_answer", args='{"field": "fee'),
            text_chunk("Mulțumesc."),
            tool_chunk(0, args='ling", "value": "ok", "clear": true, "words": "bine"}'),
            tool_chunk(1, id="c2", name="end_call", args='{"summary": "s"}'),
        ]
    )
    items = [i async for i in deepinfra("k", "m", client=client)([])]
    assert items[0] == "Mulțumesc."
    assert items[1:] == [
        ToolCall(
            "c1",
            "record_answer",
            {"field": "feeling", "value": "ok", "clear": True, "words": "bine"},
        ),
        ToolCall("c2", "end_call", {"summary": "s"}),
    ]


async def test_cut_off_tool_arguments_become_empty():
    client = FakeClient(
        [
            tool_chunk(
                0,
                id="c1",
                name="record_answer",
                args='{"field": "feeling"',
                finish="length",
            )
        ]
    )
    assert [i async for i in deepinfra("k", "m", client=client)([])] == [
        ToolCall("c1", "record_answer", {})
    ]


def test_building_without_a_key_does_not_raise():
    deepinfra("", "deepseek-ai/DeepSeek-V4-Pro")
