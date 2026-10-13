import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, in_states, timestamp_now, uuid_pk
from app.status.engine import Certainty, Question, Severity
from app.voice.calls import LIVE, CallState


class CampaignKind(StrEnum):
    heat = "heat"
    cold = "cold"


class WarningLevel(StrEnum):
    yellow = "yellow"
    red = "red"


class CallTrigger(StrEnum):
    campaign = "campaign"
    watch = "watch"
    manual = "manual"
    welcome = "welcome"
    # scripts/place_call.py's scripted calls, which no rule or call history counts (05 §1)
    test = "test"


class WelcomeOutcome(StrEnum):
    confirmed = "confirmed"
    not_available = "not_available"
    wrong_number = "wrong_number"
    no_answer = "no_answer"


class Speaker(StrEnum):
    senior = "senior"
    agent = "agent"
    system = "system"


class TurnKind(StrEnum):
    speech = "speech"
    keys = "keys"


class ReportSource(StrEnum):
    rules = "rules"
    raise_concern = "raise_concern"
    alarm_tier1 = "alarm_tier1"
    alarm_tier2 = "alarm_tier2"
    request_human = "request_human"
    trigger = "trigger"
    unanswered = "unanswered"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[CampaignKind] = mapped_column(enum_type(CampaignKind))
    level: Mapped[WarningLevel] = mapped_column(enum_type(WarningLevel))
    started_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = timestamp_now()
    # End of the active warning; watch inactivity counts only before it (G14).
    warning_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Call(Base):
    """One attempt to reach a senior; a queued row with a due time is a timer (05 §4)."""

    __tablename__ = "calls"
    __table_args__ = (
        # Never two live calls for one senior (05 §3).
        Index(
            "uq_calls_live_senior",
            "senior_id",
            unique=True,
            postgresql_where=in_states("state", LIVE),
        ),
        # The scheduler's queue: queued calls by due time.
        Index(
            "ix_calls_queued_due_at",
            "due_at",
            postgresql_where=in_states("state", frozenset({CallState.queued})),
        ),
        UniqueConstraint("twilio_call_id", name="uq_calls_twilio_call_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    senior_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seniors.id"), index=True)
    trigger: Mapped[CallTrigger] = mapped_column(enum_type(CallTrigger))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id"), index=True
    )
    # Set on a redial: each attempt is its own record (03 §9).
    previous_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("calls.id"))
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    starting_severity: Mapped[Severity] = mapped_column(enum_type(Severity))
    state: Mapped[CallState] = mapped_column(
        enum_type(CallState),
        default=CallState.queued,
        server_default=CallState.queued.name,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Twilio's CallSid; status callbacks find the call by it.
    twilio_call_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_severity: Mapped[Severity | None] = mapped_column(enum_type(Severity))
    final_certainty: Mapped[Certainty | None] = mapped_column(enum_type(Certainty))
    reason: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    welcome_outcome: Mapped[WelcomeOutcome | None] = mapped_column(
        enum_type(WelcomeOutcome)
    )
    handover_answered: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = timestamp_now()


class CallTurn(Base):
    """The transcript, one row per utterance or key press."""

    __tablename__ = "call_turns"
    __table_args__ = (
        UniqueConstraint("call_id", "position", name="uq_call_turns_call_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"))
    position: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[Speaker] = mapped_column(enum_type(Speaker))
    kind: Mapped[TurnKind] = mapped_column(enum_type(TurnKind))
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)  # from Twilio, when given
    at: Mapped[datetime] = timestamp_now()


class Answer(Base):
    """What the model extracted for one of the three questions (03 §3)."""

    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), index=True)
    field: Mapped[Question] = mapped_column(enum_type(Question))
    value: Mapped[str] = mapped_column(String(60))
    clear: Mapped[bool] = mapped_column(Boolean)
    quote: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = timestamp_now()


class StatusReport(Base):
    """Every severity reached during a call: the audit trail behind a code (05 §2)."""

    __tablename__ = "status_reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id"), index=True)
    source: Mapped[ReportSource] = mapped_column(enum_type(ReportSource))
    severity: Mapped[Severity] = mapped_column(enum_type(Severity))
    # Certainty exists only for an answered call (D7).
    certainty: Mapped[Certainty | None] = mapped_column(enum_type(Certainty))
    reason: Mapped[str] = mapped_column(String(200))
    quote: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = timestamp_now()
