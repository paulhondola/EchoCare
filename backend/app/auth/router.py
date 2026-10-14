import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller
from app.core.db import get_session
from app.seniors import forms_of_address

router = APIRouter()


class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None
    # Added with the seniors work, for caregiver and senior grants (auth-layer §3.3).
    senior_form_of_address: str | None = None
    relation: str | None = None  # caregivers


class Me(BaseModel):
    """GET /me (auth-layer §3.3). Fields are only ever added: old apps read new servers."""

    display_name: str
    phone_e164: str
    grants: list[GrantView]


@router.get("/me")
async def me(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Me:
    names = await forms_of_address(
        session, {g.senior_id for g in caller.grants if g.senior_id is not None}
    )
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[
            GrantView(
                role=g.role,
                senior_id=g.senior_id,
                senior_form_of_address=names.get(g.senior_id),
                relation=g.relation,
            )
            for g in caller.grants
        ],
    )
