"""The analysis task: states, drops, failures and who is due (design §5.3)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select

from app.core.db import Session
from app.core.settings import get_settings
from app.medical import service
from app.medical.analyzer import analyzer_agent
from app.medical.models import MedicalRecord, MedicalRecordState
from app.medical.schemas import MedicalItem, MedicalProfile
from app.medical.service import (
    ATTEMPTS,
    analyze,
    due_records,
    mark_failed,
    start_analyses,
)
from app.models import EnrollmentState
from tests.medical.test_extract import text_pdf

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TEXT = (
    "Hipertensiune arteriala, tratament zilnic cu enalapril, control periodic la medic"
)


class FakeStorage:
    is_configured = True

    def __init__(self, files: dict[str, bytes]):
        self.files = files

    async def download(self, key: str) -> bytes:
        return self.files[key]


async def no_ocr(_: bytes) -> str:
    raise AssertionError("no OCR for a text page")


def model_returning(evidence: str = "Hipertensiune") -> FunctionModel:
    def respond(messages, info: AgentInfo) -> ModelResponse:
        item = MedicalItem(
            condition="c",
            question="Ați luat pastila?",
            worrying="w",
            evidence=evidence,
            included=False,
        )
        args = MedicalProfile(items=[item]).model_dump(mode="json")
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    return FunctionModel(respond)


@pytest.fixture(autouse=True)
def fresh_state():
    service._running.clear()
    service._failures.clear()
    yield
    service._running.clear()
    service._failures.clear()


@pytest.fixture
async def add_record(db, add_senior):
    async def add(phone, enrolled=EnrollmentState.accepted, **columns):
        senior = await add_senior(phone, enrollment_state=enrolled)
        record = MedicalRecord(
            senior_id=senior.id,
            storage_key=f"k/{phone}",
            uploaded_by=senior.medic_id,
            **columns,
        )
        db.add(record)
        await db.commit()
        return record

    return add


async def reread(record_id) -> MedicalRecord | None:
    async with Session() as s:
        return await s.scalar(
            select(MedicalRecord).where(MedicalRecord.id == record_id)
        )


async def test_analysis_writes_a_profile_for_review(add_record):
    record = await add_record("+40700000201")
    storage = FakeStorage({record.storage_key: text_pdf([TEXT])})
    await analyze(record.id, storage=storage, ocr=no_ocr, model=model_returning())
    row = await reread(record.id)
    assert row.state is MedicalRecordState.review
    assert row.source_text and row.analyzed_at and row.model
    assert len(row.items) == 1 and row.items[0]["included"] is True


async def test_result_for_a_replaced_record_is_dropped(add_record):
    record = await add_record("+40700000202", source_text=TEXT)
    old_id, new_id = record.id, uuid.uuid4()
    started, gate = asyncio.Event(), asyncio.Event()
    answer = model_returning().function

    async def held(messages, info: AgentInfo) -> ModelResponse:
        started.set()
        await gate.wait()
        return answer(messages, info)

    task = asyncio.create_task(
        analyze(old_id, storage=FakeStorage({}), ocr=no_ocr, model=FunctionModel(held))
    )
    await started.wait()
    async with Session() as s:  # a new upload: a new id, pending again
        (await s.get(MedicalRecord, old_id)).id = new_id
        await s.commit()
    gate.set()
    await task
    row = await reread(new_id)
    assert row.state is MedicalRecordState.pending and row.items is None


async def test_reanalysis_skips_extraction(add_record):
    record = await add_record("+40700000203", source_text=TEXT)
    await analyze(
        record.id, storage=FakeStorage({}), ocr=no_ocr, model=model_returning()
    )
    assert (await reread(record.id)).state is MedicalRecordState.review


async def test_a_confirmed_record_is_left_alone(add_record):
    record = await add_record(
        "+40700000204", source_text=TEXT, state=MedicalRecordState.confirmed
    )
    await analyze(
        record.id, storage=FakeStorage({}), ocr=no_ocr, model=model_returning()
    )
    assert (await reread(record.id)).state is MedicalRecordState.confirmed


async def test_unreadable_pdf_ends_failed(add_record, monkeypatch):
    record = await add_record("+40700000205")
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")
    monkeypatch.setattr(
        service,
        "get_storage",
        lambda: FakeStorage({record.storage_key: b"%PDF-broken"}),
    )
    for _ in range(ATTEMPTS):
        assert await start_analyses(NOW) == 1
        await asyncio.gather(*service._running.values(), return_exceptions=True)
        await asyncio.sleep(0)
    await asyncio.gather(*service._marking)
    assert (await reread(record.id)).state is MedicalRecordState.failed
    assert await start_analyses(NOW) == 0


async def test_mark_failed_spares_a_record_no_longer_pending(add_record):
    record = await add_record("+40700000206", state=MedicalRecordState.review)
    await mark_failed(record.id)
    assert (await reread(record.id)).state is MedicalRecordState.review


async def test_no_key_starts_nothing(add_record, monkeypatch):
    await add_record("+40700000207")
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "")
    assert await start_analyses(NOW) == 0


async def test_only_accepted_or_active_seniors_are_due(db, add_record):
    first = await add_record("+40700000211", EnrollmentState.accepted)
    await add_record("+40700000212", EnrollmentState.submitted)
    second = await add_record("+40700000213", EnrollmentState.active)
    await add_record("+40700000214", EnrollmentState.withdrawn)
    async with Session() as s:
        for r, age in ((first, 2), (second, 1)):
            row = await s.get(MedicalRecord, r.id)
            row.uploaded_at = NOW - timedelta(hours=age)
        await s.commit()
    assert await due_records(db) == [first.id, second.id]


async def test_a_reanalyzed_failed_record_is_tried_again(add_record, monkeypatch):
    record = await add_record("+40700000208")
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")
    monkeypatch.setattr(
        service,
        "get_storage",
        lambda: FakeStorage({record.storage_key: b"%PDF-broken"}),
    )
    for _ in range(ATTEMPTS):
        assert await start_analyses(NOW) == 1
        await asyncio.gather(*service._running.values(), return_exceptions=True)
        await asyncio.sleep(0)
    await asyncio.gather(*service._marking)
    assert (await reread(record.id)).state is MedicalRecordState.failed
    async with Session() as s:  # what reanalyze_record does
        service.clear_analysis(await s.get(MedicalRecord, record.id))
        await s.commit()
    assert await start_analyses(NOW) == 1
    await asyncio.gather(*service._running.values(), return_exceptions=True)


async def test_at_most_max_running_start_per_tick(add_record, monkeypatch):
    for i in range(3):
        await add_record(f"+4070000022{i}")
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")
    monkeypatch.setattr(service, "get_storage", lambda: FakeStorage({}))
    never = asyncio.Event()

    async def stuck(*args, **kwargs):
        await never.wait()

    monkeypatch.setattr(service, "analyze", stuck)
    try:
        assert await start_analyses(NOW) == service.MAX_RUNNING == 2
        assert await start_analyses(NOW) == 0
    finally:
        for task in service._running.values():
            task.cancel()
        await asyncio.gather(*service._running.values(), return_exceptions=True)


async def test_a_hung_analysis_times_out_as_one_failed_attempt(add_record, monkeypatch):
    record = await add_record("+40700000230", source_text=TEXT)
    monkeypatch.setattr(get_settings(), "deepinfra_api_key", "test-key")
    monkeypatch.setattr(service, "get_storage", lambda: FakeStorage({}))
    monkeypatch.setattr(service, "ANALYSIS_TIMEOUT", 0.05)

    async def hung(messages, info: AgentInfo) -> ModelResponse:
        await asyncio.Event().wait()

    monkeypatch.setattr(
        service, "analyzer_agent", lambda _: analyzer_agent(FunctionModel(hung))
    )
    assert await start_analyses(NOW) == 1
    await asyncio.gather(*service._running.values(), return_exceptions=True)
    await asyncio.sleep(0)
    assert service._failures[record.id] == 1
    assert (await reread(record.id)).state is MedicalRecordState.pending
