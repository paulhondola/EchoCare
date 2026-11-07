import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller
from app.calls.mock import answer_mock_call, due_mock_call
from app.calls.schemas import (
    CallSummary,
    MockAnswerForm,
    MockCallView,
    TranscriptDetail,
)
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


@router.get(
    "/profile/mock-call",
    response_model=MockCallView,
    responses={204: {"description": "No call is due"}},
)
async def get_mock_call(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """The call the senior's app shows as a card, never in production (design §4.2)."""
    view = await due_mock_call(session, caller)
    return view if view is not None else Response(status_code=204)


@router.post("/calls/{call_id}/mock-answer", status_code=204)
async def post_mock_answer(
    call_id: uuid.UUID,
    form: MockAnswerForm,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """The senior answers the card; the call ends through the shared step (design §5)."""
    await answer_mock_call(session, caller, call_id, form)
