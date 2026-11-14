import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller
from app.core.db import get_session
from app.core.storage import StorageService, get_storage
from app.export.schemas import SeniorExport
from app.export.service import export_senior

router = APIRouter(tags=["seniors"])


@router.get("/seniors/{senior_id}/export", response_model=SeniorExport)
async def export(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> SeniorExport:
    """Exports the senior and everything stored about them as JSON, by the registering
    medic or DAS past `draft` (GDPR Art. 15 & 20; 04 §1, design 2026-11-14)."""
    return await export_senior(session, caller, senior_id, storage)
