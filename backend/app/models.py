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
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import (
    ROLE_ORDER,
    SENIOR_ROLES,
    Grant,
    Role,
    User,
)
from app.db import Base
from app.incidents.models import (
    UNRESOLVED,
    Event,
    EventType,
    Incident,
    IncidentEvent,
    IncidentOutcome,
    IncidentStatus,
)
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Senior,
    SeniorStatus,
    WatchCondition,
    WatchState,
)
from app.voice.models import (
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


__all__ = [
    "ROLE_ORDER",
    "SENIOR_ROLES",
    "UNRESOLVED",
    "Answer",
    "Base",
    "Call",
    "CallTrigger",
    "CallTurn",
    "Campaign",
    "CampaignKind",
    "Consent",
    "ConsentDecision",
    "ConsentMethod",
    "EnrollmentState",
    "Event",
    "EventType",
    "Grant",
    "Incident",
    "IncidentEvent",
    "IncidentOutcome",
    "IncidentStatus",
    "PushToken",
    "ReportSource",
    "Role",
    "Senior",
    "SeniorStatus",
    "Speaker",
    "StatusReport",
    "StoredEnum",
    "TurnKind",
    "User",
    "WarningLevel",
    "WatchCondition",
    "WatchState",
    "WelcomeOutcome",
    "enum_type",
    "in_states",
    "timestamp_now",
    "uuid_pk",
]
