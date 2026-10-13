import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, Role
from app.auth.service import Caller, current_caller, refuse, require_roles
from app.core.db import get_session
from app.seniors.models import EnrollmentState, Senior
from app.seniors.service import (
    CaregiverForm,
    CaregiverView,
    SeniorForm,
    SeniorSummary,
    SeniorView,
    enrollments_query,
    has_caregiver,
    missing_address,
    missing_to_submit,
    move,
    own_senior,
    reach_senior,
    senior_view,
    seniors_query,
    sync_senior_grant,
)
from app.staff.service import user_for

log = logging.getLogger("sentinela.seniors")

router = APIRouter()


@router.get("/seniors")
async def list_seniors(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SeniorSummary]:
    """The seniors in the caller's reach, by name (04 §1, auth-layer §3.6)."""
    seniors = await session.scalars(seniors_query(caller))
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
    senior = Senior(medic_id=caller.user.id, **body.columns())
    session.add(senior)
    await session.flush()  # the database makes the id
    await sync_senior_grant(session, senior)
    await session.commit()
    return await senior_view(session, senior)


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
    senior = await own_senior(session, caller, senior_id)  # locked: no move meanwhile
    if senior.enrollment_state not in (
        EnrollmentState.draft,
        EnrollmentState.submitted,
    ):
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "wrong_state")
    missing = missing_address(body)
    if senior.enrollment_state == EnrollmentState.submitted and missing:
        log.info("refused incomplete: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(422, "incomplete", missing=missing)
    updated = await session.scalar(
        update(Senior)
        .where(Senior.id == senior_id)
        .values(**body.columns())
        .returning(Senior)
        .execution_options(populate_existing=True)
    )
    await sync_senior_grant(session, updated)
    await session.commit()
    return await senior_view(session, updated)


@router.post("/seniors/{senior_id}/caregivers", status_code=201)
async def add_caregiver(
    senior_id: uuid.UUID,
    body: CaregiverForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CaregiverView:
    """The number becomes a caregiver grant for this senior (UC-01 step 3). No notice
    SMS yet. A number already caring for this senior is `already_done`."""
    await own_senior(session, caller, senior_id)
    user = await user_for(session, body.phone, body.display_name)
    granted = await session.scalar(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.caregiver,
            senior_id=senior_id,
            relation=body.relation,
            granted_by=caller.user.id,
        )
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        await session.rollback()
        raise refuse(409, "already_done")
    await session.commit()
    return CaregiverView(
        user_id=user.id,
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        relation=body.relation,
    )


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
    senior = await own_senior(session, caller, senior_id)
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior_id,
            Grant.user_id == user_id,
            Grant.role == Role.caregiver,
        )
    )
    if senior.enrollment_state != EnrollmentState.draft and not await has_caregiver(
        session, senior_id
    ):
        log.info("refused incomplete: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(422, "incomplete", missing=["caregiver"])
    await session.commit()
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
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state == EnrollmentState.draft:
        missing = await missing_to_submit(session, senior)
        if missing:
            log.info(
                "refused incomplete: user %s, senior %s", caller.user.id, senior_id
            )
            raise refuse(422, "incomplete", missing=missing)
    await move(
        session, caller, senior, EnrollmentState.draft, EnrollmentState.submitted
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


@router.post("/seniors/{senior_id}/accept")
async def accept_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorSummary:
    """Acceptă: submitted -> accepted (UC-04 step 1). The welcome call is not queued
    yet; until it exists, `accepted` is the last state a senior reaches."""
    senior = await reach_senior(session, caller, senior_id)
    await move(
        session, caller, senior, EnrollmentState.submitted, EnrollmentState.accepted
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


@router.get("/enrollments")
async def list_enrollments(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SeniorSummary]:
    """Cereri de înrolare: the seniors in `submitted`, oldest first (04 §1)."""
    seniors = await session.scalars(enrollments_query())
    return [SeniorSummary.model_validate(s, from_attributes=True) for s in seniors]
