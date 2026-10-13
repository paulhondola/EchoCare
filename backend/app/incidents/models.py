import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, in_states, timestamp_now, uuid_pk


class EventType(StrEnum):
    high_pulse_at_rest = "high_pulse_at_rest"
    inactivity = "inactivity"
    sos_button = "sos_button"
    manual_request = "manual_request"  # "Sunați-mă" (05 §4)


class IncidentOutcome(StrEnum):
    senior_ok = "senior_ok"
    team_sent = "team_sent"
    called_112 = "called_112"
    not_reached = "not_reached"
    false_alarm = "false_alarm"


class IncidentStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


# At most one per senior, enforced by a partial unique index (05 §3).
UNRESOLVED = frozenset({IncidentStatus.open, IncidentStatus.in_progress})


class Event(Base):
    """A watch anomaly, a button press or a "Sunați-mă" request (05 §2).

    The id is generated on the device, so a resent event is a duplicate key (05 §3).
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    senior_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seniors.id"), index=True)
    type: Mapped[EventType] = mapped_column(enum_type(EventType))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = timestamp_now()
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The phone's last known location, stored only with an event (05 §4).
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float)
    located_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # GET /incidents/{id} looks up the events of an incident's calls.
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calls.id"), index=True
    )


IncidentEvent = Event


class Incident(Base):
    """DAS's handling of one red (G16, UC-11)."""

    __tablename__ = "incidents"
    __table_args__ = (
        # At most one unresolved incident per senior (05 §3).
        Index(
            "uq_incidents_unresolved_senior",
            "senior_id",
            unique=True,
            postgresql_where=in_states("status", UNRESOLVED),
        ),
        CheckConstraint(
            "status != 'resolved' OR (resolved_by IS NOT NULL AND outcome IS NOT NULL)",
            name="ck_incidents_resolved_has_outcome",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    senior_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seniors.id"), index=True)
    opened_by_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calls.id"))
    status: Mapped[IncidentStatus] = mapped_column(
        enum_type(IncidentStatus),
        default=IncidentStatus.open,
        server_default=IncidentStatus.open.name,
    )
    reason: Mapped[str] = mapped_column(String(200))
    opened_at: Mapped[datetime] = timestamp_now()
    taken_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[IncidentOutcome | None] = mapped_column(enum_type(IncidentOutcome))
    note: Mapped[str | None] = mapped_column(Text)
