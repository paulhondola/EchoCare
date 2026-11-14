"""Schemas for GET /api/seniors/{senior_id}/export (GDPR Art. 15 & 20; 04 §1)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.medical.schemas import MedicalRecordView
from app.seniors.models import EcgClassification, HealthReadingKind
from app.seniors.schemas import Code, RoomView, SeniorView, State, WatchView


class ExportStatus(BaseModel):
    code: Code
    reason: str
    since: datetime
    source_call_id: uuid.UUID | None


class ExportConsent(BaseModel):
    id: uuid.UUID
    decision: State
    method: State
    text_version: str
    call_id: uuid.UUID | None
    evidence: dict[str, Any] | None
    signature_strokes: list[Any] | None
    at: datetime


class ExportSummary(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID
    previous_id: uuid.UUID | None
    content: dict[str, Any]
    model: str
    created_at: datetime


class ExportWatchReading(BaseModel):
    id: int
    measured_at: datetime
    pulse: int | None
    resting_pulse: int | None
    steps_today: int | None
    battery: int | None
    worn: bool | None


class ExportHealthReading(BaseModel):
    id: uuid.UUID
    kind: HealthReadingKind
    measured_at: datetime
    received_at: datetime
    spo2: int | None
    ecg_classification: EcgClassification | None
    ecg_heart_rate: int | None
    ecg_trace: list[int] | None
    ecg_trace_hz: int | None


class ExportWatch(BaseModel):
    state: WatchView | None
    readings: list[ExportWatchReading]
    health_readings: list[ExportHealthReading] = []


class ExportEvent(BaseModel):
    id: uuid.UUID
    type: State
    source: str | None
    measured_at: datetime
    received_at: datetime
    snapshot: dict[str, Any] | None
    latitude: float | None
    longitude: float | None
    location_accuracy_m: float | None
    located_at: datetime | None
    call_id: uuid.UUID | None


class ExportIncident(BaseModel):
    id: uuid.UUID
    opened_by_call_id: uuid.UUID | None
    status: State
    reason: str
    opened_at: datetime
    taken_at: datetime | None
    resolved_at: datetime | None
    outcome: State | None
    note: str | None


class ExportTurn(BaseModel):
    position: int
    speaker: State
    kind: State
    content: str
    confidence: float | None
    at: datetime


class ExportAnswer(BaseModel):
    field: State
    value: str
    clear: bool
    quote: str | None
    at: datetime


class ExportReport(BaseModel):
    source: State
    severity: Code
    certainty: Code | None
    reason: str
    quote: str | None
    at: datetime


class ExportCall(BaseModel):
    id: uuid.UUID
    trigger: State
    campaign_id: uuid.UUID | None
    previous_call_id: uuid.UUID | None
    attempt: int
    starting_severity: Code
    state: State
    due_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    final_severity: Code | None
    final_certainty: Code | None
    reason: str | None
    summary: str | None
    welcome_outcome: State | None
    handover_answered: bool | None
    turns: list[ExportTurn]
    answers: list[ExportAnswer]
    reports: list[ExportReport]


class SeniorExport(BaseModel):
    exported_at: datetime
    senior: SeniorView
    status: ExportStatus | None
    consents: list[ExportConsent]
    summaries: list[ExportSummary]
    medical_record: MedicalRecordView | None
    watch: ExportWatch
    # The home node's latest reading, the only one kept (P20, 05 §4)
    room: RoomView | None = None
    events: list[ExportEvent]
    incidents: list[ExportIncident]
    calls: list[ExportCall]
