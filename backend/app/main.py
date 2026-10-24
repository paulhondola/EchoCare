import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.calls.router import router as calls_router
from app.campaigns.router import router as campaigns_router
from app.core.settings import check_environment, get_settings
from app.incidents.router import router as incidents_router
from app.scheduler.loop import run
from app.seniors.router import router as seniors_router
from app.system.router import router as system_router
from app.voice.router import router as voice_router

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("echocare").setLevel(logging.INFO)
logging.getLogger("echocare.incidents").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """The scheduler loop (06 §1) lives as long as the app does."""
    task = asyncio.create_task(run()) if settings.scheduler_enabled else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="EchoCare",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


# Assemble domain routers onto /api
api.include_router(auth_router)
api.include_router(seniors_router)
api.include_router(incidents_router)
api.include_router(campaigns_router)
api.include_router(calls_router)
api.include_router(voice_router)
api.include_router(system_router)

# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)

__all__ = ["app"]
