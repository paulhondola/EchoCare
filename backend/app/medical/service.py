import asyncio
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from functools import cache

from pydantic_ai.models import Model
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse
from app.core.changes import Change, ChangeKind, note
from app.core.db import Session
from app.core.llm import deepinfra_model
from app.core.settings import get_settings
from app.core.storage import StorageError, StorageService, get_storage
from app.medical.analyzer import analyzer_agent, prompt
from app.medical.extract import Ocr, deepinfra_ocr, extract_text
from app.medical.models import MedicalRecord, MedicalRecordState
from app.medical.schemas import MedicalConfirmForm, MedicalItem, MedicalRecordView
from app.seniors.models import EnrollmentState, Senior
from app.seniors.service import own_senior, reach

log = logging.getLogger("echocare.medical")

MAX_BYTES = 10 * 1024 * 1024
URL_SECONDS = 600
ANALYZABLE = {EnrollmentState.accepted, EnrollmentState.active}
ATTEMPTS = 3
ANALYSIS_TIMEOUT = 300  # seconds: a hung OCR or model call must free its slot
MAX_RUNNING = 2  # analyses in flight: each holds a PDF of up to 10 MB

# Per process, as the summaries' (design §5.3): a restart forgets the failures.
_running: dict[uuid.UUID, asyncio.Task] = {}  # by record id
_failures: Counter[uuid.UUID] = Counter()  # by record id
_marking: set[asyncio.Task] = set()  # kept so a task is not collected before it ends


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
    await uploadable(session, caller, senior_id)
    if len(pdf) > MAX_BYTES:
        raise refuse(413, "too_large")
    if not pdf.startswith(b"%PDF"):
        raise refuse(415, "not_pdf")
    # No row stays locked while S3 works: other writers of the senior must not wait on
    # a slow upload. The file goes under a new key, so nothing reads it until the swap.
    await session.commit()
    new_id = uuid.uuid4()
    key = storage_key(senior_id, new_id)
    try:
        await storage.upload(key, pdf, "application/pdf")
    except StorageError as e:
        log.warning("upload failed for senior %s: %s", senior_id, e)
        raise refuse(503, "storage_unavailable") from e
    try:
        # Locked again for the swap, and the state checked again: it may have moved.
        await uploadable(session, caller, senior_id)
    except Exception:
        await forget(storage, key)
        raise
    # An analysis of the old file that finishes after this matches nothing once the id
    # has changed, instead of leaving its text or profile here.
    record = await session.scalar(
        select(MedicalRecord)
        .where(MedicalRecord.senior_id == senior_id)
        .with_for_update()
    )
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
        await forget(storage, old_key)
    return await view_of(record, storage, full=True)


async def uploadable(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> None:
    """The caller's own senior, locked, in a state that takes a record."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state in {EnrollmentState.refused, EnrollmentState.withdrawn}:
        raise refuse(409, "wrong_state")


async def forget(storage: StorageService, key: str) -> None:
    try:
        await storage.delete(key)
    except StorageError:
        log.warning("could not delete record file %s", key)


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


async def record_states(
    session: AsyncSession, caller: Caller
) -> dict[uuid.UUID, MedicalRecordState]:
    """The state of each record of a senior this caller registered, for the medic home's
    tasks on GET /seniors rows (04 §1, design 2026-11-13). Nobody else's, as on the record."""
    if Role.medic not in caller.roles:
        return {}
    rows = await session.execute(
        select(MedicalRecord.senior_id, MedicalRecord.state)
        .join(Senior, Senior.id == MedicalRecord.senior_id)
        .where(Senior.medic_id == caller.user.id)
    )
    return dict(rows.tuples().all())


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
    # The profile the medic's screen showed: a newer analysis is not confirmed with its
    # questions. Optional, so an app that sends none keeps the count check alone.
    stale = form.analyzed_at is not None and form.analyzed_at != record.analyzed_at
    if stale or len(form.items) != len(stored):
        raise refuse(409, "wrong_state")
    record.items = [
        {
            **old,
            "included": new.included,
            "question": new.question,
            "worrying": new.worrying or old["worrying"],
        }
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


async def due_records(session: AsyncSession) -> list[uuid.UUID]:
    """Pending records of seniors who can be analyzed, oldest upload first."""
    rows = await session.scalars(
        select(MedicalRecord.id)
        .join(Senior, Senior.id == MedicalRecord.senior_id)
        .where(
            MedicalRecord.state == MedicalRecordState.pending,
            Senior.enrollment_state.in_(ANALYZABLE),
        )
        .order_by(MedicalRecord.uploaded_at, MedicalRecord.id)
    )
    return [i for i in rows if i not in _running and _failures[i] < ATTEMPTS]


async def analyze(
    record_id: uuid.UUID, *, storage: StorageService, ocr: Ocr, model: Model
) -> None:
    """Read the PDF's text, run the analyzer, store the profile for review. Owns its
    sessions, holding none while the PDF, OCR or the model work (design §5.3)."""
    async with Session() as session:
        record = await session.get(MedicalRecord, record_id)
        if record is None or record.state is not MedicalRecordState.pending:
            log.info("record %s is gone or not pending, skipped", record_id)
            return
        senior_id, key, text = record.senior_id, record.storage_key, record.source_text
    if text is None:
        text = await extract_text(await storage.download(key), ocr)
        async with Session() as session:
            await session.execute(
                update(MedicalRecord)
                .where(
                    MedicalRecord.id == record_id,
                    MedicalRecord.state == MedicalRecordState.pending,
                )
                .values(source_text=text)
            )
            await session.commit()
    profile = (await analyzer_agent(model).run(prompt(text), deps=text)).output
    async with Session() as session:
        record = await session.scalar(
            select(MedicalRecord)
            .where(
                MedicalRecord.id == record_id,
                MedicalRecord.state == MedicalRecordState.pending,
            )
            .with_for_update()
        )
        if record is None:
            log.info("record %s changed while analyzing, result dropped", record_id)
            return
        record.items = [
            i.model_copy(update={"included": True}).model_dump(mode="json")
            for i in profile.items
        ]
        record.model = model.model_name
        record.analyzed_at = datetime.now(UTC)
        record.state = MedicalRecordState.review
        note(session, Change(ChangeKind.medical_record, senior_id))
        await session.commit()
    log.info("record %s analyzed, %d items", record_id, len(profile.items))


async def mark_failed(record_id: uuid.UUID) -> None:
    async with Session() as session:
        await session.execute(
            update(MedicalRecord)
            .where(
                MedicalRecord.id == record_id,
                MedicalRecord.state == MedicalRecordState.pending,
            )
            .values(state=MedicalRecordState.failed)
        )
        await session.commit()
    _failures.pop(record_id, None)  # a reanalysis starts over
    log.error("record %s failed after %d attempts", record_id, ATTEMPTS)


def _finished(record_id: uuid.UUID, task: asyncio.Task) -> None:
    _running.pop(record_id, None)
    if task.cancelled():
        return
    e = task.exception()
    if e is None:
        _failures.pop(record_id, None)
    else:
        _failures[record_id] += 1
        log.error("analysis failed, record %s: %s", record_id, type(e).__name__)
        if _failures[record_id] >= ATTEMPTS:
            marking = asyncio.create_task(mark_failed(record_id))
            _marking.add(marking)
            marking.add_done_callback(_marking.discard)


@cache  # built once, so analyses reuse their connections
def clients(api_key: str, model: str, ocr_model: str) -> tuple[Model, Ocr]:
    return deepinfra_model(api_key, model), deepinfra_ocr(api_key, ocr_model)


async def start_analyses(now: datetime) -> int:
    """The scheduler step: start one task per due record and return; never awaits one."""
    settings = get_settings()
    storage = get_storage()
    if not settings.deepinfra_api_key or not storage.is_configured:
        return 0
    async with Session() as session:
        due = await due_records(session)
    due = due[: max(MAX_RUNNING - len(_running), 0)]
    if not due:
        return 0
    model, ocr = clients(
        settings.deepinfra_api_key, settings.summary_model, settings.ocr_model
    )
    for record_id in due:
        task = asyncio.create_task(
            asyncio.wait_for(
                analyze(record_id, storage=storage, ocr=ocr, model=model),
                ANALYSIS_TIMEOUT,
            )
        )
        _running[record_id] = task
        task.add_done_callback(lambda t, r=record_id: _finished(r, t))
    return len(due)


async def stop_analyses() -> None:
    """On shutdown: cancel the tasks under way; the next copy redoes their records."""
    tasks = [*_running.values(), *_marking]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
