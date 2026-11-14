import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.calls.router import router as calls_router
from app.campaigns.router import router as campaigns_router
from app.core.settings import AppEnv, check_environment, cors_origins, get_settings
from app.erasure.router import router as erasure_router
from app.export.router import router as export_router
from app.incidents.router import router as incidents_router
from app.medical.router import router as medical_router
from app.medical.service import stop_analyses
from app.memory.service import stop_summaries
from app.notify.service import drain, install, sender_from
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
if not settings.deepinfra_api_key:
    # Every wellbeing call would end dropped at the senior's first reply (04 §5).
    logging.getLogger("echocare").error(
        "DEEPINFRA_API_KEY is not set: the agent loop cannot talk and summaries are off"
    )
# Pushes after every commit (04 §6), when a credential is set.
install(sender_from(settings.firebase_push_credentials))


def docs_urls(env: AppEnv) -> dict[str, str | None]:
    """Swagger, ReDoc and the schema, except in production, where they would list the
    whole API surface to anyone (design 2026-11-14)."""
    if env is AppEnv.production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/api/docs",
        "redoc_url": "/api/redoc",
        "openapi_url": "/api/openapi.json",
    }


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """The scheduler loop (06 §1) lives as long as the app does; pushes under way
    finish before it ends."""
    task = asyncio.create_task(run()) if settings.scheduler_enabled else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await stop_summaries()  # a summary under way is redone by the next copy
    await stop_analyses()  # likewise: the next copy redoes it
    await drain()  # the pushes already under way


# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(title="EchoCare", lifespan=lifespan, **docs_urls(settings.app_env))
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(settings),
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


# Assemble domain routers onto /api
api.include_router(auth_router)
api.include_router(seniors_router)
api.include_router(medical_router)
api.include_router(erasure_router)
api.include_router(export_router)
api.include_router(incidents_router)
api.include_router(campaigns_router)
api.include_router(calls_router)
api.include_router(voice_router)
api.include_router(system_router)

# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)

__all__ = ["app"]
