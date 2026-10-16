import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, current_caller, require_roles
from app.core.db import get_session
from app.seniors.schemas import (
    CaregiverForm,
    CaregiverView,
    SeniorForm,
    SeniorSummary,
    SeniorView,
)
from app.seniors.service import (
    accept,
    edit,
    enrollments_query,
    grant_caregiver,
    reach_senior,
    register,
    revoke_caregiver,
    senior_view,
    seniors_query,
    submit,
)

router = APIRouter()


@router.get("/seniors")
async def list_seniors(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
    role: Role | None = None,
) -> list[SeniorSummary]:
    """The seniors in the caller's reach, by name (04 §1, auth-layer §3.6). `role`
    narrows the list to one role's reach, for that role's home (seniors SE6)."""
    seniors = await session.scalars(seniors_query(caller, role))
    return [SeniorSummary.model_validate(s, from_attributes=True) for s in seniors]


@router.get("/seniors/{senior_id}")
async def get_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorView:
    return await senior_view(session, await reach_senior(session, caller, senior_id))


@router.post("/seniors", status_code=201)
async def create_senior(
    body: SeniorForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorView:
    """Pacient nou: a draft, seen only by its medic until submitted (UC-01)."""
    return await register(session, caller, body)


@router.put("/seniors/{senior_id}")
async def update_senior(
    senior_id: uuid.UUID,
    body: SeniorForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorView:
    """The whole registration again, while it is a draft or a request DAS has not
    accepted yet (04 §2). A request keeps its place and stays one DAS can act on: an
    edit that drops the address is `incomplete`."""
    return await edit(session, caller, senior_id, body)


@router.post("/seniors/{senior_id}/caregivers", status_code=201)
async def add_caregiver(
    senior_id: uuid.UUID,
    body: CaregiverForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CaregiverView:
    """The number becomes a caregiver grant for this senior (UC-01 step 3). No notice
    SMS yet. A number already caring for this senior is `already_done`."""
    return await grant_caregiver(session, caller, senior_id, body)


@router.delete("/seniors/{senior_id}/caregivers/{user_id}", status_code=204)
async def remove_caregiver(
    senior_id: uuid.UUID,
    user_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Deletes the grant, so access stops at once (05 §5). The user row stays; with no
    grant left their next request is `not_registered`. A repeat changes nothing. Past
    draft, the last caregiver stays: removing them is `incomplete` (04 §2)."""
    await revoke_caregiver(session, caller, senior_id, user_id)
    return Response(status_code=204)


@router.post("/seniors/{senior_id}/submit")
async def submit_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorSummary:
    """draft -> submitted: DAS can see her from now on (UC-01 step 6, auth-layer §3.6).

    A registration missing what DAS needs is 422 `incomplete`, naming what is missing.
    """
    return await submit(session, caller, senior_id)


@router.post("/seniors/{senior_id}/accept")
async def accept_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorSummary:
    """Acceptă: submitted -> accepted (UC-04 step 1). The welcome call is not queued
    yet; until it exists, `accepted` is the last state a senior reaches."""
    return await accept(session, caller, senior_id)


@router.get("/enrollments")
async def list_enrollments(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SeniorSummary]:
    """Cereri de înrolare: the seniors in `submitted`, oldest first (04 §1)."""
    seniors = await session.scalars(enrollments_query())
    return [SeniorSummary.model_validate(s, from_attributes=True) for s in seniors]
