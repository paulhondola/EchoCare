import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type, timestamp_now, uuid_pk


class CampaignKind(StrEnum):
    heat = "heat"
    cold = "cold"


class WarningLevel(StrEnum):
    yellow = "yellow"
    red = "red"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[CampaignKind] = mapped_column(enum_type(CampaignKind))
    level: Mapped[WarningLevel] = mapped_column(enum_type(WarningLevel))
    started_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = timestamp_now()
    # End of the active warning; watch inactivity counts only before it (G14).
    warning_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
