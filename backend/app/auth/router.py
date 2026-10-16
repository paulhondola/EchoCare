from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import GrantView, ProfileView
from app.auth.service import (
    Caller,
    current_caller,
    drop_push_token,
    save_push_token,
)
from app.core.db import get_session
from app.seniors.service import forms_of_address

router = APIRouter()


@router.get("/profile")
async def profile(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileView:
    names = await forms_of_address(
        session, {g.senior_id for g in caller.grants if g.senior_id is not None}
    )
    return ProfileView(
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


# A longer token would overflow push_tokens.token, a String(512).
Token = Annotated[str, Path(max_length=512)]


@router.put("/profile/push-tokens/{token}", status_code=204)
async def put_push_token(
    token: Token,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Stores this device's push token; a shared device's token moves to its latest
    user (G4, Q19)."""
    await save_push_token(session, caller, token)


@router.delete("/profile/push-tokens/{token}", status_code=204)
async def delete_push_token(
    token: Token,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Forgets the caller's own token, 204 whether or not it was there (G4, Q19)."""
    await drop_push_token(session, caller, token)
