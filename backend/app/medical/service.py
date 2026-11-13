import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse
from app.core.storage import StorageError, StorageService
from app.medical.models import MedicalRecord, MedicalRecordState
from app.medical.schemas import MedicalConfirmForm, MedicalItem, MedicalRecordView
from app.seniors.models import EnrollmentState, Senior
from app.seniors.service import own_senior, reach

log = logging.getLogger("echocare.medical")

MAX_BYTES = 10 * 1024 * 1024
URL_SECONDS = 600
ANALYZABLE = {EnrollmentState.accepted, EnrollmentState.active}


def storage_key(senior_id: uuid.UUID, record_id: uuid.UUID) -> str:
    return f"medical-records/{senior_id}/{record_id}.pdf"


async def view_of(
    record: MedicalRecord, storage: StorageService, *, full: bool
) -> MedicalRecordView:
    """`full` is the registering medic's view; DAS gets it only once confirmed."""
    shown = full or record.state is MedicalRecordState.confirmed
    pdf_url = None
    if shown:
        try:
            pdf_url = await storage.generate_presigned_url(
                record.storage_key, URL_SECONDS
            )
        except StorageError:
            log.warning("no pdf url for record %s", record.id)
    return MedicalRecordView(
        state=record.state,
        uploaded_at=record.uploaded_at,
        analyzed_at=record.analyzed_at,
        confirmed_at=record.confirmed_at,
        items=[MedicalItem.model_validate(i) for i in record.items]
        if shown and record.items is not None
        else None,
        pdf_url=pdf_url,
    )


def clear_analysis(record: MedicalRecord) -> None:
    record.state = MedicalRecordState.pending
    record.items = None
    record.model = None
    record.analyzed_at = None
    record.confirmed_at = None
    record.confirmed_by = None


async def current_record(session: AsyncSession, senior_id: uuid.UUID):
    return await session.scalar(
        select(MedicalRecord).where(MedicalRecord.senior_id == senior_id)
    )


async def upload_record(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    pdf: bytes,
    storage: StorageService,
) -> MedicalRecordView:
    """Attach a PDF, replacing the current one; analysis starts over (design §5.4)."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state in {
        EnrollmentState.refused,
        EnrollmentState.withdrawn,
    }:
        raise refuse(409, "wrong_state")
    if len(pdf) > MAX_BYTES:
        raise refuse(413, "too_large")
    if not pdf.startswith(b"%PDF"):
        raise refuse(415, "not_pdf")
    record = await current_record(session, senior_id)
    new_id = uuid.uuid4()
    key = storage_key(senior_id, new_id)
    try:
        await storage.upload(key, pdf, "application/pdf")
    except StorageError as e:
        log.warning("upload failed for senior %s: %s", senior_id, e)
        raise refuse(503, "storage_unavailable") from e
    old_key = record.storage_key if record else None
    if record is None:
        record = MedicalRecord(senior_id=senior_id, uploaded_by=caller.user.id)
        session.add(record)
    record.id = new_id
    record.storage_key = key
    record.uploaded_by = caller.user.id
    record.uploaded_at = datetime.now(UTC)
    record.source_text = None
    clear_analysis(record)
    await session.commit()
    if old_key:
        try:
            await storage.delete(old_key)
        except StorageError:
            log.warning("could not delete old record file %s", old_key)
    return await view_of(record, storage, full=True)


async def record_for(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    storage: StorageService,
) -> MedicalRecordView | None:
    """For the registering medic and DAS past `draft`; others get 404 (design §5.4)."""
    senior: Senior | None = await session.scalar(
        select(Senior).where(
            Senior.id == senior_id,
            reach(caller, Role.medic) | reach(caller, Role.das),
        )
    )
    if senior is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    record = await current_record(session, senior_id)
    if record is None:
        return None
    registering = Role.medic in caller.roles and senior.medic_id == caller.user.id
    return await view_of(record, storage, full=registering)


async def analyzable_record(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    states: set[MedicalRecordState],
) -> MedicalRecord:
    senior = await own_senior(session, caller, senior_id)
    record = await current_record(session, senior_id)
    if (
        senior.enrollment_state not in ANALYZABLE
        or record is None
        or record.state not in states
    ):
        raise refuse(409, "wrong_state")
    return record


async def confirm_record(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    form: MedicalConfirmForm,
    storage: StorageService,
) -> MedicalRecordView:
    """The medic's edits and choices become the questions DAS and calls use."""
    record = await analyzable_record(
        session,
        caller,
        senior_id,
        {MedicalRecordState.review, MedicalRecordState.confirmed},
    )
    stored = record.items or []
    if len(form.items) != len(stored):
        raise refuse(409, "wrong_state")
    record.items = [
        {**old, "included": new.included, "question": new.question}
        for old, new in zip(stored, form.items, strict=True)
    ]
    record.state = MedicalRecordState.confirmed
    record.confirmed_at = datetime.now(UTC)
    record.confirmed_by = caller.user.id
    await session.commit()
    return await view_of(record, storage, full=True)


async def reanalyze_record(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    storage: StorageService,
) -> MedicalRecordView:
    """Back to `pending`; the scheduler analyzes the kept text again (design §5.2)."""
    record = await analyzable_record(
        session,
        caller,
        senior_id,
        {
            MedicalRecordState.review,
            MedicalRecordState.confirmed,
            MedicalRecordState.failed,
        },
    )
    clear_analysis(record)
    await session.commit()
    return await view_of(record, storage, full=True)


async def confirmed_checks(
    session: AsyncSession, senior_id: uuid.UUID
) -> list[tuple[str, str]]:
    """(question, worrying) of the included items of a confirmed record, in order."""
    record = await current_record(session, senior_id)
    if record is None or record.state is not MedicalRecordState.confirmed:
        return []
    items = [MedicalItem.model_validate(i) for i in record.items or []]
    return [(i.question, i.worrying) for i in items if i.included]
