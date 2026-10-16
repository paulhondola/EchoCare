import uuid
from datetime import datetime

from pydantic import BaseModel

from app.incidents.schemas import CallDetail, Level


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
