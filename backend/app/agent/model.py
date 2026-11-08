"""One streamed model round from DeepInfra's OpenAI-compatible API (04 §5)."""

import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import openai

from app.agent.tools import TOOLS

log = logging.getLogger(__name__)

BASE_URL = "https://api.deepinfra.com/v1/openai"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


# Yields text pieces as they stream ("" for a chunk with none), then the round's complete
# tool calls in index order.
ModelStream = Callable[[list[dict[str, Any]]], AsyncIterator[str | ToolCall]]


def _arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def deepinfra(api_key: str, model: str, *, client: Any = None) -> ModelStream:
    async def stream(messages: list[dict[str, Any]]) -> AsyncIterator[str | ToolCall]:
        nonlocal client
        if client is None:  # lazily, so building without a key never raises
            client = openai.AsyncOpenAI(base_url=BASE_URL, api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            stream=True,
            temperature=0.3,
            max_tokens=1000,
            extra_body={"reasoning_effort": "none"},
        )
        calls: dict[int, dict[str, str]] = {}
        try:
            async for chunk in response:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                # Every chunk yields, "" for a tool-call piece, so the loop's timeout
                # sees a stream that is still alive (design §4).
                yield choice.delta.content or ""
                for piece in choice.delta.tool_calls or []:
                    call = calls.setdefault(
                        piece.index, {"id": "", "name": "", "args": ""}
                    )
                    call["id"] = piece.id or call["id"]
                    if piece.function:
                        call["name"] += piece.function.name or ""
                        call["args"] += piece.function.arguments or ""
                if choice.finish_reason == "length":
                    log.warning("model round cut off at max_tokens")
        finally:  # an interrupt closes the HTTP stream now, not at GC
            await response.aclose()
        for index in sorted(calls):
            call = calls[index]
            yield ToolCall(
                call["id"] or f"call_{index}", call["name"], _arguments(call["args"])
            )

    return stream
