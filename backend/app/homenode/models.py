import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, enum_type


class NodeCondition(StrEnum):
    ok = "ok"
    offline = "offline"


class RoomState(StrEnum):
    """FastAPI's answer to a room reading (P26). The node shows it with its body; only
    `cold` and `hot` held for the hold time start a call (P21)."""

    ok = "ok"
    cold_soon = "cold_soon"
    cold = "cold"
    hot_soon = "hot_soon"
    hot = "hot"


class HomeNodeState(Base):
    """The home node's latest room reading, one row per senior with a node (P20, 05 §2).

    Only the latest is kept (05 §4). `out_of_range_since` and `out_of_range_event_sent`
    carry the hold time across readings, so one stretch out of range is one event (P21).
    """

    __tablename__ = "home_node_states"

    senior_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("seniors.id"), primary_key=True
    )
    state: Mapped[NodeCondition] = mapped_column(enum_type(NodeCondition))
    last_reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_pct: Mapped[float | None] = mapped_column(Float)
    last_motion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The node's own prediction of the room in an hour (P26)
    forecast_60m_c: Mapped[float | None] = mapped_column(Float)
    out_of_range_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    out_of_range_event_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    # One inactivity event per warning, until motion is seen again (04 §3)
    inactivity_event_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
