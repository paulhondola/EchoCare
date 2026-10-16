import time
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import Role
from app.auth.service import Caller, require_roles
from app.core.settings import get_settings
from app.system.schemas import DatabaseHealthView, SystemHealthView
from app.system.service import check_database_health

router = APIRouter()
settings = get_settings()


@router.get("/system/health")
async def system_health(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
) -> SystemHealthView:
    """Dashboard system health telemetry for DAS (04 §1)."""
    t0 = time.perf_counter()
    now = datetime.now(UTC)
    try:
        latency_ms = await check_database_health()
        db_health = DatabaseHealthView(status="ok", latency_ms=latency_ms)
        status: Literal["ok", "degraded"] = "ok"
    except SQLAlchemyError, OSError:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        db_health = DatabaseHealthView(status="unreachable", latency_ms=latency_ms)
        status = "degraded"

    return SystemHealthView(
        status=status,
        env=settings.app_env,
        database=db_health,
        timestamp=now,
    )
