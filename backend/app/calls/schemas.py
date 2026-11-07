import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.incidents.schemas import CallDetail, Level

Day = Literal[
    "luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică", "unknown"
]


class CallSummary(BaseModel):
    """One row of GET /seniors/{id}/calls (04 §1)."""

    id: uuid.UUID
    trigger: str
    state: str
    due_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    final_severity: Level | None
    final_certainty: Level | None
    reason: str | None
    summary: str | None


class AnswerView(BaseModel):
    """What the model extracted for one of the three questions (05 §2)."""

    field: str
    value: str
    clear: bool
    quote: str
    at: datetime


class TranscriptDetail(CallDetail):
    """GET /calls/{id}/transcript: the incident page's call, plus the answers."""

    answers: list[AnswerView]


class MockCallView(BaseModel):
    """GET /profile/mock-call: the call the senior's app shows as a card (design §4.2).

    The app shows exactly what the server sends, so a consent's recorded `text_version`
    matches what the senior read.
    """

    call_id: uuid.UUID
    trigger: str
    campaign_kind: str | None = None
    campaign_level: str | None = None
    consent_text: str | None = None
    text_version: str | None = None


class MockAnswerForm(BaseModel):
    """POST /calls/{id}/mock-answer: one shape per trigger (design §4.2)."""

    feeling: Literal["ok", "unwell"] | None = None
    day: Day | None = None
    shelter: Literal["yes", "no"] | None = None
    declined: bool = False  # „Nu acum”
    consent: bool | None = None
