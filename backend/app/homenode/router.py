from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, require_roles
from app.core.db import get_session
from app.homenode.schemas import RoomReadingForm, RoomReadingView
from app.homenode.service import record_room_reading

router = APIRouter()


@router.post("/me/room-readings")
async def send_room_reading(
    body: RoomReadingForm,
    caller: Annotated[Caller, Depends(require_roles(Role.senior))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoomReadingView:
    """The home node's reading, relayed by the senior's phone (UC-16, 04 §3). Answers
    with the room state the phone writes back to the node (P26)."""
    senior_id = next(g.senior_id for g in caller.grants if g.role == Role.senior)
    return await record_room_reading(session, senior_id, body, datetime.now(UTC))
