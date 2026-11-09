"""One streamed model round through Pydantic AI's model layer (04 §5, design §8).

Only the request: the turn control stays in loop.py, so no Agent and no agent graph.
"""

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from pydantic_ai.direct import model_request_stream
from pydantic_ai.messages import (
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings

from app.agent.tools import TOOL_DEFS

log = logging.getLogger(__name__)

SETTINGS = ModelSettings(
    temperature=0.3, max_tokens=1000, extra_body={"reasoning_effort": "none"}
)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


# Yields text pieces as they stream ("" for an event with none), then the round's complete
# tool calls in order.
ModelStream = Callable[[list[ModelMessage]], AsyncIterator[str | ToolCall]]


def _arguments(part: ToolCallPart) -> dict[str, Any]:
    try:
        return part.args_as_dict(raise_if_invalid=True)
    except ValueError, AssertionError:  # cut off, or not an object
        return {}


def stream_with(model: Model) -> ModelStream:
    async def stream(messages: list[ModelMessage]) -> AsyncIterator[str | ToolCall]:
        # Leaving early (an interrupt) exits the `async with`, which closes the HTTP
        # stream now, not at GC.
        async with model_request_stream(
            model,
            messages,
            model_settings=SETTINGS,
            model_request_parameters=ModelRequestParameters(function_tools=TOOL_DEFS),
        ) as s:
            async for event in s:
                if isinstance(event, PartStartEvent) and isinstance(
                    event.part, TextPart
                ):
                    yield event.part.content
                elif isinstance(event, PartDeltaEvent) and isinstance(
                    event.delta, TextPartDelta
                ):
                    yield event.delta.content_delta
                else:
                    # Tool-call pieces too, so the loop's timeout sees a stream that is
                    # still alive (design §4).
                    yield ""
            response = s.get()
        if response.finish_reason == "length":
            log.warning("model round cut off at max_tokens")
        for part in response.parts:
            if isinstance(part, ToolCallPart):
                yield ToolCall(part.tool_call_id, part.tool_name, _arguments(part))

    return stream
