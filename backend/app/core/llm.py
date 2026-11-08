"""The DeepInfra model shared by the summary agents (design §3, 04 §5)."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

BASE_URL = "https://api.deepinfra.com/v1/openai"


def deepinfra_model(api_key: str, name: str) -> OpenAIChatModel:
    # The OpenAI client refuses an empty key at construction; a call made with the
    # placeholder fails instead, and the caller's failure path handles that.
    return OpenAIChatModel(
        name, provider=OpenAIProvider(base_url=BASE_URL, api_key=api_key or "missing")
    )
