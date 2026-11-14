import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller
from app.core.db import get_session
from app.core.storage import StorageService, get_storage
from app.erasure.service import delete_pdf, erase_senior

router = APIRouter(tags=["seniors"])


@router.post("/seniors/{senior_id}/erase", status_code=204)
async def erase(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> Response:
    """Deletes the senior and everything about them, the medical record PDF included,
    by the registering medic or DAS past `draft` (04 §2, design 2026-11-14). Refused
    with `call_live` or `incident_open`; a repeat is 404."""
    key = await erase_senior(session, caller, senior_id)
    if key:
        await delete_pdf(storage, senior_id, key)
    return Response(status_code=204)
