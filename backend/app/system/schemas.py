from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DatabaseHealthView(BaseModel):
    status: Literal["ok", "unreachable"]
    latency_ms: float | None = None


class SystemHealthView(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    database: DatabaseHealthView
    timestamp: datetime
