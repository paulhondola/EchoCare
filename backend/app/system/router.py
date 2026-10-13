import time
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import Role
from app.auth.service import Caller, require_roles
from app.core.settings import get_settings
from app.system.models import DatabaseHealth, SystemHealth
from app.system.service import check_database_health

router = APIRouter()
settings = get_settings()


@router.get("/system/health")
async def system_health(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
) -> SystemHealth:
    """Dashboard system health telemetry for DAS (04 §1)."""
    t0 = time.perf_counter()
    now = datetime.now(UTC)
    try:
        latency_ms = await check_database_health()
        db_health = DatabaseHealth(status="ok", latency_ms=latency_ms)
        status: Literal["ok", "degraded"] = "ok"
    except SQLAlchemyError, OSError:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        db_health = DatabaseHealth(status="unreachable", latency_ms=latency_ms)
        status = "degraded"

    return SystemHealth(
        status=status,
        env=settings.app_env,
        database=db_health,
        timestamp=now,
    )
