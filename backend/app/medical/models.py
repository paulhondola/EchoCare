import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, timestamp_now, uuid_pk


class MedicalRecordState(StrEnum):
    pending = "pending"
    review = "review"
    confirmed = "confirmed"
    failed = "failed"


class MedicalRecord(Base):
    """A senior's medical record PDF and the check questions drawn from it; one current
    row per senior, a new upload replaces its content (design §5.1)."""

    __tablename__ = "medical_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    senior_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seniors.id", ondelete="CASCADE"), unique=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = timestamp_now()
    state: Mapped[MedicalRecordState] = mapped_column(
        enum_type(MedicalRecordState),
        default=MedicalRecordState.pending,
        server_default=MedicalRecordState.pending.name,
    )
    # Never logged, never served: kept for re-analysis and the citation check.
    source_text: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
