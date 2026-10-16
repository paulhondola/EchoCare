import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller
from app.calls.schemas import CallSummary, TranscriptDetail
from app.calls.service import call_history, transcript
from app.core.db import get_session

router = APIRouter()


@router.get("/seniors/{senior_id}/calls")
async def list_calls(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CallSummary]:
    """The senior's calls, newest first, for anyone who reaches her (04 §1)."""
    return await call_history(session, caller, senior_id)


@router.get("/calls/{call_id}/transcript")
async def get_transcript(
    call_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TranscriptDetail:
    """The turns, reports and answers of one call: her medic and DAS only (04 §1)."""
    return await transcript(session, caller, call_id)
