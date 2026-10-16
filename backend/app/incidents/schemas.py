import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, StringConstraints

from app.incidents.models import IncidentOutcome, IncidentStatus
from app.seniors.schemas import CaregiverSummary, SeniorDetail

# Severity and Certainty are IntEnums; clients read their names, "red", not "2".
Level = Annotated[str, BeforeValidator(lambda v: getattr(v, "name", v))]


# One row of GET /incidents (04 §1). Names follow the incidents and seniors tables (05 §1)
# and match the dashboard's Incident type (dashboard/src/api.ts).
class IncidentSummary(BaseModel):
    id: uuid.UUID
    senior_full_name: str
    senior_form_of_address: str
    status: IncidentStatus
    reason: str
    opened_at: datetime
    taken_by_name: str | None
    taken_at: datetime | None
    handover_answered: bool


Note = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class ResolutionForm(BaseModel):
    """POST /incidents/{id}/resolve's body (04 §2)."""

    outcome: IncidentOutcome
    note: Note


class TriggerEventView(BaseModel):
    """The event that queued the opening call, with the phone's location if it had one."""

    type: str
    measured_at: datetime
    latitude: float | None
    longitude: float | None
    location_accuracy_m: float | None
    located_at: datetime | None


class TurnView(BaseModel):
    speaker: str
    kind: str
    content: str
    at: datetime


class ReportView(BaseModel):
    """A severity reached during the call, with the senior's words (05 §2)."""

    source: str
    severity: Level
    certainty: Level | None
    reason: str
    quote: str | None
    at: datetime


class CallDetail(BaseModel):
    id: uuid.UUID
    trigger: str
    attempt: int
    state: str
    started_at: datetime | None
    ended_at: datetime | None
    final_severity: Level | None
    final_certainty: Level | None
    reason: str | None
    summary: str | None
    handover_answered: bool | None
    reports: list[ReportView]
    turns: list[TurnView]


class IncidentDetail(BaseModel):
    id: uuid.UUID
    status: str
    reason: str
    opened_at: datetime
    taken_by_name: str | None
    taken_at: datetime | None
    resolved_by_name: str | None
    resolved_at: datetime | None
    outcome: str | None
    note: str | None
    handover_answered: bool
    senior: SeniorDetail
    caregivers: list[CaregiverSummary]
    event: TriggerEventView | None
    calls: list[CallDetail]
