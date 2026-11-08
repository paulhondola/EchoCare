"""The DeepInfra model shared by the summary agents (design §3, 04 §5)."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

BASE_URL = "https://api.deepinfra.com/v1/openai"


def deepinfra_model(
    api_key: str, name: str, *, provider: OpenAIProvider | None = None
) -> OpenAIChatModel:
    """`provider` is for tests, to record the request (design §8, 11)."""
    # The OpenAI client refuses an empty key at construction; a call made with the
    # placeholder fails instead, and the caller's failure path handles that.
    provider = provider or OpenAIProvider(
        base_url=BASE_URL, api_key=api_key or "missing"
    )
    # The token cap goes out as `max_tokens`, as PR #62 sent it (design §8, 11).
    profile = OpenAIModelProfile(openai_chat_supports_max_completion_tokens=False)
    return OpenAIChatModel(name, provider=provider, profile=profile)
