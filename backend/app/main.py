import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import Role
from app.auth.router import router as auth_router
from app.auth.service import Caller, require_roles
from app.core.db import engine
from app.core.settings import check_environment, get_settings
from app.incidents.router import (
    incidents_query,
    parse_statuses,
)
from app.incidents.router import (
    router as incidents_router,
)
from app.seniors.router import router as seniors_router
from app.staff.router import router as staff_router
from app.voice.router import router as voice_router

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)
logging.getLogger("sentinela.incidents").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)

# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="Sentinela",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


@api.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env}


class DatabaseHealth(BaseModel):
    status: Literal["ok", "unreachable"]
    latency_ms: float | None = None


class SystemHealth(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    database: DatabaseHealth
    timestamp: datetime


async def check_database_health() -> float:
    """Executes SELECT 1 on the database and returns latency in milliseconds."""
    t0 = time.perf_counter()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return round((time.perf_counter() - t0) * 1000, 2)


@api.get("/system/health")
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


# Assemble domain routers onto /api
api.include_router(auth_router)
api.include_router(staff_router)
api.include_router(seniors_router)
api.include_router(incidents_router)
api.include_router(voice_router)

# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)

__all__ = ["app", "incidents_query", "parse_statuses"]
