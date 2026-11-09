"""The four tools' arguments, as the model sees them (04 §5); CallRules checks each value."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_WORDS = "The senior's exact words."
_REASON = "A short reason."


class RecordAnswerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["feeling", "orientation", "shelter"]
    value: str = Field(
        description="feeling: ok or unwell. shelter: yes or no. "
        "orientation: the day of the week the senior named, or unknown."
    )
    clear: bool = Field(description="True only if the answer is clear and certain.")
    words: str = Field(description=_WORDS)


class RaiseConcernArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["yellow", "red"]
    reason: str = Field(description=_REASON)
    words: str = Field(description=_WORDS)


class RequestHumanArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(description=_REASON)


class EndCallArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(description="One sentence, in Romanian.")
