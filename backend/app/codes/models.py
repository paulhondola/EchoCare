"""The senior's code and the status reports behind it (03, 05 §2). Owned here: only
this package writes `senior_statuses` and `status_reports` (ADR-005)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, timestamp_now, uuid_pk
from app.status.engine import Certainty, Severity


class ReportSource(StrEnum):
    rules = "rules"
    raise_concern = "raise_concern"
    alarm_tier1 = "alarm_tier1"
    alarm_tier2 = "alarm_tier2"
    request_human = "request_human"
    trigger = "trigger"
    unanswered = "unanswered"


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
