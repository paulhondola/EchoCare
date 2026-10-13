from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    status: Literal["ok", "unreachable"]
    latency_ms: float | None = None


class SystemHealth(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    database: DatabaseHealth
    timestamp: datetime
