from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import GrantView, MeView
from app.auth.service import Caller, current_caller
from app.core.db import get_session
from app.seniors.service import forms_of_address

router = APIRouter()


@router.get("/me")
async def me(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MeView:
    names = await forms_of_address(
        session, {g.senior_id for g in caller.grants if g.senior_id is not None}
    )
    return MeView(
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
