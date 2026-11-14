import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, Field, StringConstraints

from app.incidents.models import EventType, IncidentOutcome, IncidentStatus
from app.seniors.schemas import CaregiverSummary, SeniorDetail, SummaryVersionView

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


class EventSnapshotForm(BaseModel):
    """What the device saw when the event fired (04 §3). Every field optional: older clients
    send none; a pulse event sets pulse and resting_baseline; a fall sets its own fields. The
    service stores it as-is on the Event row."""

    pulse: int | None = None
    resting_baseline: int | None = None
    moving: bool | None = None
    minutes_without_steps: int | None = None
    battery: int | None = None
    # A fall seen by the watch (P19)
    lowest_acceleration_g: float | None = None
    peak_acceleration_g: float | None = None
    seconds_of_stillness: float | None = None
    # A fall found by the home node's floor search (P24, 08-ecou.md §3.2): where the
    # object was, and the sweep that found it, from 0° to 180° in 5° steps, in metres.
    object_angle_deg: Annotated[float, Field(ge=0, le=180)] | None = None
    object_distance_m: Annotated[float, Field(ge=0, le=10)] | None = None
    seconds_still: float | None = None
    scan: (
        Annotated[list[Annotated[float, Field(ge=0, le=10)]], Field(max_length=73)]
        | None
    ) = None


class EventForm(BaseModel):
    """POST /me/events' body (04 §3). „Sunați-mă”, falls and the watch's own anomalies; the id
    is the device's, so a resend is a duplicate. `measured_at` carries an offset: a naive time
    is 422. `source`, `snapshot` and location are all optional for backward compatibility."""

    id: uuid.UUID
    type: Literal[
        EventType.manual_request,
        EventType.fall,
        EventType.high_pulse_at_rest,
        EventType.inactivity,
    ]
    measured_at: AwareDatetime
    source: Literal["watch", "phone", "home_node"] | None = None
    snapshot: EventSnapshotForm | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_accuracy_m: float | None = None


class EventView(BaseModel):
    """Whether the event queued a call, and the call it started or joined, if any."""

    queued: bool
    call_id: uuid.UUID | None


class TriggerEventView(BaseModel):
    """The event that queued the opening call, with the phone's location if it had one.

    For a fall found by the home node, also where it found the object and the sweep, so
    the dashboard can draw the room (P24, 08-ecou.md §3.3); null otherwise."""

    type: str
    measured_at: datetime
    latitude: float | None
    longitude: float | None
    location_accuracy_m: float | None
    located_at: datetime | None
    source: str | None = None
    object_angle_deg: float | None = None
    object_distance_m: float | None = None
    scan: list[float] | None = None


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
    summary: SummaryVersionView | None = None
