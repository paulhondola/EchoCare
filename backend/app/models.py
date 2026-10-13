"""Tables (05 §1), with the rules the database enforces itself (05 §3).

The database makes every row id with uuidv7(), built into Postgres 18 (04 §0); only an
event's id comes from the device. Enums are stored as their member names in a plain
VARCHAR with no CHECK constraint, so a later change can add a value without a migration
(ADR-001 §2.3: changes only add), and a name this copy does not know reads back as a plain
string instead of failing. `grants.role` predates this and keeps its CHECK.
"""

import enum
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import (  # noqa: F401
    ROLE_ORDER,
    SENIOR_ROLES,
    Grant,
    Role,
    User,
)
from app.db import Base
from app.incidents import UNRESOLVED, IncidentStatus
from app.status import Severity
from app.voice.models import (  # noqa: F401
    Answer,
    Call,
    CallTrigger,
    CallTurn,
    Campaign,
    CampaignKind,
    ReportSource,
    Speaker,
    StatusReport,
    TurnKind,
    WarningLevel,
    WelcomeOutcome,
)


class EnrollmentState(StrEnum):
    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    active = "active"
    refused = "refused"
    wrong_number = "wrong_number"
    unreachable = "unreachable"


class ConsentDecision(StrEnum):
    given = "given"
    refused = "refused"
    withdrawn = "withdrawn"


class ConsentMethod(StrEnum):
    call = "call"
    signature = "signature"
    medic = "medic"


class WatchCondition(StrEnum):
    ok = "ok"
    not_worn = "not_worn"
    offline = "offline"


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


class StoredEnum(TypeDecorator):
    """An enum in a VARCHAR(32), by member name, so Severity and Certainty store "green"
    and "high", not 0 and 2. An unknown name, written by a newer copy during a deploy or
    before a rollback, reads back as the bare string (ADR-001 §2.3).
    """

    # ponytail: autogenerate renders this as app.models.StoredEnum; write sa.String(32).
    impl = String
    cache_ok = True

    def __init__(self, cls: type[enum.Enum]) -> None:
        super().__init__(length=32)
        self.cls = cls

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return value.name if isinstance(value, enum.Enum) else value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return value if value is None else self.cls.__members__.get(value, value)


def enum_type(cls: type[enum.Enum]) -> StoredEnum:
    return StoredEnum(cls)


def in_states(column: str, states: frozenset[Any]) -> Any:
    """A partial index predicate over a set of enum members, in a stable order."""
    names = ", ".join(f"'{name}'" for name in sorted(state.name for state in states))
    return text(f"{column} IN ({names})")


def uuid_pk() -> Mapped[uuid.UUID]:
    # Time-ordered, so new rows land at the end of the primary key index.
    return mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))


def timestamp_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Senior(Base):
    __tablename__ = "seniors"

    id: Mapped[uuid.UUID] = uuid_pk()
    medic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    form_of_address: Mapped[str] = mapped_column(String(120))  # "doamna Maria"
    phone_e164: Mapped[str] = mapped_column(String(16))
    phone_is_landline: Mapped[bool] = mapped_column(Boolean)
    # Structured address and access details for DAS (G13).
    street: Mapped[str | None] = mapped_column(String(200))
    street_number: Mapped[str | None] = mapped_column(String(20))
    block: Mapped[str | None] = mapped_column(String(20))
    staircase: Mapped[str | None] = mapped_column(String(20))
    floor: Mapped[str | None] = mapped_column(String(20))
    apartment: Mapped[str | None] = mapped_column(String(20))
    intercom_code: Mapped[str | None] = mapped_column(String(40))
    key_holder: Mapped[str | None] = mapped_column(String(200))
    landmark: Mapped[str | None] = mapped_column(String(200))
    # Collected, unused in the MVP (05 §4).
    call_window: Mapped[str | None] = mapped_column(String(60))
    enrollment_state: Mapped[EnrollmentState] = mapped_column(
        enum_type(EnrollmentState),
        default=EnrollmentState.draft,
        server_default=EnrollmentState.draft.name,
    )
    created_at: Mapped[datetime] = timestamp_now()


class Consent(Base):
    """Every consent decision, as a history: a withdrawal is a new row (05 §4)."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = uuid_pk()
    senior_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seniors.id"), index=True)
    decision: Mapped[ConsentDecision] = mapped_column(enum_type(ConsentDecision))
    method: Mapped[ConsentMethod] = mapped_column(enum_type(ConsentMethod))
    text_version: Mapped[str] = mapped_column(String(40))
    call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calls.id"))
    # Keys or words and Twilio's confidence, for method call (G7).
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    signature_strokes: Mapped[list[Any] | None] = mapped_column(JSONB)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = timestamp_now()


class WatchState(Base):
    """The latest check-in only; no history of readings (05 §4, §5)."""

    __tablename__ = "watch_states"

    senior_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seniors.id"), primary_key=True
    )
    state: Mapped[WatchCondition] = mapped_column(enum_type(WatchCondition))
    last_check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    battery: Mapped[int | None] = mapped_column(Integer)
    worn: Mapped[bool | None] = mapped_column(Boolean)
    last_pulse: Mapped[int | None] = mapped_column(Integer)


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


class SeniorStatus(Base):
    """The current code, one row per active senior; the most frequent read (05 §4)."""

    __tablename__ = "senior_statuses"

    senior_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seniors.id"), primary_key=True
    )
    code: Mapped[Severity] = mapped_column(enum_type(Severity))
    reason: Mapped[str] = mapped_column(String(200))
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calls.id"))


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


class PushToken(Base):
    """Where to deliver pushes for a user, one row per device (G4)."""

    __tablename__ = "push_tokens"
    __table_args__ = (UniqueConstraint("token", name="uq_push_tokens_token"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # A device's token belongs to whoever signed in on it last.
    token: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
