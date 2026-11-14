import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, current_caller, require_roles
from app.calls.service import (
    cancel_queued_calls,
    queue_welcome_call,
    welcome_call_pending,
)
from app.core.db import get_session
from app.core.storage import StorageService, get_storage
from app.erasure.service import delete_pdf
from app.medical.service import record_key, record_states
from app.seniors.schemas import (
    CaregiverEditForm,
    CaregiverForm,
    CaregiverView,
    CheckInForm,
    SeniorForm,
    SeniorSummary,
    SeniorView,
    SignatureForm,
    SummaryVersionView,
    WatchReadingView,
    WatchView,
)
from app.seniors.service import (
    accept,
    call_again,
    delete_draft,
    edit,
    edit_caregiver,
    enrollments_query,
    grant_caregiver,
    reach_senior,
    record_check_in,
    register,
    revoke_caregiver,
    save_signature,
    senior_summaries,
    senior_view,
    submit,
    summary_for,
    watch_readings,
    watch_state,
    watch_view,
    withdraw_consent,
)
from app.voice.service import call_in_progress

router = APIRouter()


@router.get("/seniors")
async def list_seniors(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
    role: Role | None = None,
) -> list[SeniorSummary]:
    """The seniors in the caller's reach, by name (04 §1, auth-layer §3.6). `role`
    narrows the list to one role's reach, for that role's home (seniors SE6)."""
    rows = await senior_summaries(session, caller, role)
    # `seniors` can't import `medical` (ADR-005); the router composes them
    states = await record_states(session, caller)
    for row in rows:
        row.medical_record_state = states.get(row.id)
    return rows


@router.get("/seniors/{senior_id}")
async def get_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorView:
    senior = await reach_senior(session, caller, senior_id)
    view = await senior_view(session, senior)
    # `seniors` can't import `voice` (ADR-005); the router composes them
    view.call_in_progress = await call_in_progress(session, senior_id)
    view.watch_state, view.last_pulse = await watch_state(session, caller, senior)
    return view


@router.get(
    "/seniors/{senior_id}/watch",
    response_model=WatchView,
    responses={204: {"description": "No check-in yet, or the watch is not shown"}},
)
async def get_watch(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """The watch's latest check-in (04 §1, ADR-006)."""
    senior = await reach_senior(session, caller, senior_id)
    view = await watch_view(session, caller, senior)
    return view if view else Response(status_code=204)


@router.get("/seniors/{senior_id}/watch/readings")
async def get_watch_readings(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WatchReadingView]:
    """The last 24 hours of check-ins, in 5-minute buckets (04 §1, ADR-006)."""
    senior = await reach_senior(session, caller, senior_id)
    return await watch_readings(session, caller, senior, datetime.now(UTC))


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
    caller: Annotated[Caller, Depends(require_roles(Role.medic, Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorView:
    """The whole registration again, in any state, by the registering medic or DAS
    (SE9, 04 §2). Past draft the address stays: an edit that drops it is
    `incomplete`."""
    return await edit(session, caller, senior_id, body)


@router.delete("/seniors/{senior_id}", status_code=204)
async def delete_senior(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> Response:
    """Deletes a draft with its consents and grants, by its registering medic (Q10),
    and its medical record PDF (design 2026-11-14). Past draft, or once a call refers
    to the senior, it is 409 `wrong_state`. A repeat is 404, the row being gone."""
    key = await record_key(session, senior_id)  # the record cascades with the senior
    await delete_draft(session, caller, senior_id)
    if key:
        await delete_pdf(storage, senior_id, key)
    return Response(status_code=204)


@router.post("/seniors/{senior_id}/caregivers", status_code=201)
async def add_caregiver(
    senior_id: uuid.UUID,
    body: CaregiverForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic, Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CaregiverView:
    """The number becomes a caregiver grant for this senior (UC-01 step 3), added by
    the registering medic or DAS (SE9). No notice SMS yet. A number already caring for
    this senior is `already_done`."""
    return await grant_caregiver(session, caller, senior_id, body)


@router.patch("/seniors/{senior_id}/caregivers/{user_id}")
async def update_caregiver(
    senior_id: uuid.UUID,
    user_id: uuid.UUID,
    body: CaregiverEditForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic, Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CaregiverView:
    """The caregiver's name and relation, whichever is given, by the registering medic
    or DAS (SE9, Q13). The name is the user's, so it changes everywhere. A staff
    member's name stays theirs: 403 `not_allowed` (Q22). Not her caregiver: 404."""
    return await edit_caregiver(session, caller, senior_id, user_id, body)


@router.delete("/seniors/{senior_id}/caregivers/{user_id}", status_code=204)
async def remove_caregiver(
    senior_id: uuid.UUID,
    user_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic, Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """Deletes the grant, so access stops at once (05 §5), for the registering medic or
    DAS (SE9). The user row stays; with no grant left their next request is
    `not_registered`. A repeat changes nothing. Past draft, the last caregiver stays:
    removing them is `incomplete` (04 §2)."""
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
    """Acceptă: submitted -> accepted (UC-04 step 1). The welcome call is queued now, in
    the same transaction (04 §2); the senior answers it from the app's card."""
    return await accept(session, caller, senior_id, then=queue_welcome_call)


@router.post("/seniors/{senior_id}/welcome-call")
async def welcome_call_again(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorSummary:
    """Sună din nou: `wrong_number` or `unreachable` -> `accepted`, and a new welcome
    call queued in the same transaction (UC-04, 04 §2). A repeat answers the same and
    queues nothing; any other state is `wrong_state`."""
    return await call_again(
        session,
        caller,
        senior_id,
        then=queue_welcome_call,
        pending=welcome_call_pending,
    )


@router.post("/seniors/{senior_id}/consent-withdrawn")
async def withdraw_senior_consent(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.medic, Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeniorSummary:
    """active -> withdrawn, recorded by the registering medic or DAS (Q15). Adds a
    `withdrawn` consent row and cancels the senior's queued calls in the same
    transaction. Already withdrawn is `already_done`; any other state, `wrong_state`."""
    return await withdraw_consent(session, caller, senior_id, then=cancel_queued_calls)


@router.post("/seniors/{senior_id}/signature", status_code=204)
async def sign_senior_consent(
    senior_id: uuid.UUID,
    body: SignatureForm,
    caller: Annotated[Caller, Depends(require_roles(Role.medic))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """The senior's signature as a consent row, by the registering medic, while she is
    `draft`, `submitted` or `accepted` (Q16). The latest one counts, so a repeat adds a
    row rather than being refused."""
    await save_signature(session, caller, senior_id, body)
    return Response(status_code=204)


@router.get("/enrollments")
async def list_enrollments(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[SeniorSummary]:
    """Cereri de înrolare: the seniors in `submitted`, oldest first (04 §1)."""
    seniors = await session.scalars(enrollments_query())
    return [SeniorSummary.model_validate(s, from_attributes=True) for s in seniors]


@router.post("/me/check-ins", status_code=204)
async def check_in(
    body: CheckInForm,
    caller: Annotated[Caller, Depends(require_roles(Role.senior))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """The watch's latest reading, relayed by the senior's phone (UC-13). Keeps only
    the latest; an older one than the stored is ignored."""
    senior_id = next(g.senior_id for g in caller.grants if g.role == Role.senior)
    await record_check_in(session, senior_id, body, datetime.now(UTC))


@router.get(
    "/seniors/{senior_id}/summary",
    response_model=SummaryVersionView,
    responses={204: {"description": "No summary yet"}},
)
async def get_summary(
    senior_id: uuid.UUID,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """The DAS briefing: the latest summary, for her medic and DAS (04 §1, design §5 B)."""
    view = await summary_for(session, caller, senior_id)
    return view if view is not None else Response(status_code=204)
