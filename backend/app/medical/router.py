import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import Caller, current_caller, refuse
from app.core.db import get_session
from app.core.storage import StorageService, get_storage
from app.medical.schemas import MedicalConfirmForm, MedicalRecordView
from app.medical.service import (
    MAX_BYTES,
    confirm_record,
    reanalyze_record,
    record_for,
    upload_record,
)

router = APIRouter(tags=["medical"])

Session = Annotated[AsyncSession, Depends(get_session)]
Who = Annotated[Caller, Depends(current_caller)]
Storage = Annotated[StorageService, Depends(get_storage)]


@router.put("/seniors/{senior_id}/medical-record")
async def put_medical_record(
    senior_id: uuid.UUID,
    request: Request,
    caller: Who,
    session: Session,
    storage: Storage,
) -> MedicalRecordView:
    """Attach the senior's record PDF as the raw body (04 §2, design §5.4)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise refuse(413, "too_large")
    # current_caller's read opened a transaction: end it, so no pooled connection sits
    # idle in it while a slow body streams; caller stays loaded (expire_on_commit=False).
    await session.commit()
    # Counted as it arrives: a chunked body has no Content-Length to trust.
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BYTES:
            raise refuse(413, "too_large")
    return await upload_record(session, caller, senior_id, bytes(body), storage)


@router.get(
    "/seniors/{senior_id}/medical-record",
    response_model=MedicalRecordView,
    responses={204: {"description": "No record yet"}},
)
async def get_medical_record(
    senior_id: uuid.UUID, caller: Who, session: Session, storage: Storage
):
    """The record and its questions, for her medic and DAS past `draft` (04 §1)."""
    view = await record_for(session, caller, senior_id, storage)
    return view if view is not None else Response(status_code=204)


@router.post("/seniors/{senior_id}/medical-record/confirm")
async def post_confirm(
    senior_id: uuid.UUID,
    form: MedicalConfirmForm,
    caller: Who,
    session: Session,
    storage: Storage,
) -> MedicalRecordView:
    return await confirm_record(session, caller, senior_id, form, storage)


@router.post("/seniors/{senior_id}/medical-record/reanalyze")
async def post_reanalyze(
    senior_id: uuid.UUID, caller: Who, session: Session, storage: Storage
) -> MedicalRecordView:
    return await reanalyze_record(session, caller, senior_id, storage)
