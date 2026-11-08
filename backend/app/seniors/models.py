import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, timestamp_now, uuid_pk


class EnrollmentState(StrEnum):
    draft = "draft"
    submitted = "submitted"
    accepted = "accepted"
    active = "active"
    refused = "refused"
    wrong_number = "wrong_number"
    unreachable = "unreachable"
    withdrawn = "withdrawn"


class ConsentDecision(StrEnum):
    given = "given"
    refused = "refused"
    withdrawn = "withdrawn"


class ConsentMethod(StrEnum):
    call = "call"
    signature = "signature"
    medic = "medic"
    das = "das"
    app = "app"  # given or refused on the mock card in the senior's app (design §4.4)


class WatchCondition(StrEnum):
    ok = "ok"
    not_worn = "not_worn"
    offline = "offline"


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
    # Stamped by the move to `submitted` and to `accepted` (05 §1).
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


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


class SummaryVersion(Base):
    """One version of a senior's summary, one per call; never updated (design §4, 05 §2)."""

    __tablename__ = "senior_summaries"

    id: Mapped[uuid.UUID] = uuid_pk()
    senior_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seniors.id"), index=True)
    # The call this version came from; unique, so a call is summarized once.
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), unique=True)
    previous_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("senior_summaries.id")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = timestamp_now()
