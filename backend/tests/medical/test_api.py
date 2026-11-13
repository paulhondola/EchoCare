"""The medical record endpoints (design §5.4, 04 §1, §2)."""

import asyncio

import pytest
from sqlalchemy import select

from app.core.storage import StorageError, get_storage
from app.main import app
from app.medical.models import MedicalRecord, MedicalRecordState
from app.medical.service import (
    MAX_BYTES,
    analyze,
    confirmed_checks,
    mark_failed,
    storage_key,
)
from app.models import EnrollmentState, Grant, Role
from tests.medical.test_analysis import TEXT, model_returning, no_ocr
from tests.medical.test_analysis import FakeStorage as OldFile
from tests.medical.test_extract import text_pdf
from tests.seniors.test_seniors import NOT_FOUND, refusal, signed_in

MEDIC = "+40700000301"
DAS = "+40700000302"
OTHER_MEDIC = "+40700000303"
SENIOR = "+40700000304"
PDF = b"%PDF-1.7 test"
STORED = [
    {
        "condition": "Diabet",
        "question": "Ați luat insulina?",
        "worrying": "Nu a luat insulina",
        "evidence": "diabet zaharat tip 2",
        "included": True,
    },
    {
        "condition": "Hipertensiune",
        "question": "Vă doare capul?",
        "worrying": "Dureri de cap",
        "evidence": "HTA",
        "included": True,
    },
]


class FakeStorage:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.down = False

    def _check(self):
        if self.down:
            raise StorageError("down")

    async def upload(self, key, data, content_type="application/octet-stream"):
        self._check()
        self.files[key] = data

    async def delete(self, key):
        self._check()
        self.files.pop(key, None)

    async def generate_presigned_url(self, key, expires_in=3600):
        self._check()
        return f"https://s3.test/{key}"


@pytest.fixture
def storage():
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    return fake


@pytest.fixture
async def medic(add_user):
    return await add_user(MEDIC, Role.medic)


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das)


@pytest.fixture
async def senior(add_senior, medic):
    return await add_senior(SENIOR, medic=medic)  # draft


@pytest.fixture
async def active(add_active_senior, medic):
    return await add_active_senior(SENIOR, medic=medic)


def url(senior, tail=""):
    return f"/api/seniors/{senior.id}/medical-record{tail}"


def put_pdf(client, senior, body=PDF, token=MEDIC):
    return client.put(url(senior), content=body, headers=signed_in(token))


def get_record(client, senior, token=MEDIC):
    return client.get(url(senior), headers=signed_in(token))


def command(client, senior, tail, json=None, token=MEDIC):
    return client.post(url(senior, tail), json=json, headers=signed_in(token))


async def seed(
    db, senior, state, items=STORED, key="medical-records/old.pdf", text="text"
):
    db.add(
        MedicalRecord(
            senior_id=senior.id,
            storage_key=key,
            uploaded_by=senior.medic_id,
            state=state,
            source_text=text,
            items=items,
        )
    )
    await db.commit()


async def row(db, senior) -> MedicalRecord:
    return await db.scalar(
        select(MedicalRecord)
        .where(MedicalRecord.senior_id == senior.id)
        .execution_options(populate_existing=True)
    )


async def test_medic_uploads_a_pdf(client, storage, senior):
    r = await put_pdf(client, senior)
    assert r.status_code == 200
    assert r.json()["state"] == "pending" and r.json()["items"] is None
    assert list(storage.files.values()) == [PDF]


async def test_upload_refusals(client, storage, db, add_user, senior):
    assert (await put_pdf(client, senior, b"hello")).json()["detail"]["reason"] == (
        "not_pdf"
    )
    assert (
        await put_pdf(client, senior, b"%PDF" + b"0" * MAX_BYTES)
    ).status_code == 413
    await add_user(OTHER_MEDIC, Role.medic)
    assert refusal(await put_pdf(client, senior, token=OTHER_MEDIC)) == NOT_FOUND
    storage.down = True
    r = await put_pdf(client, senior)
    assert (r.status_code, r.json()["detail"]["reason"]) == (503, "storage_unavailable")
    assert await row(db, senior) is None
    senior.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    storage.down = False
    r = await put_pdf(client, senior)
    assert (r.status_code, r.json()["detail"]["reason"]) == (409, "wrong_state")


async def test_a_new_upload_resets_the_record_and_drops_the_old_file(
    client, storage, db, active
):
    await seed(db, active, MedicalRecordState.confirmed)
    old_id = (await row(db, active)).id
    storage.files["medical-records/old.pdf"] = b"old"
    r = await put_pdf(client, active)
    assert r.json()["state"] == "pending" and r.json()["items"] is None
    assert "medical-records/old.pdf" not in storage.files
    assert len(storage.files) == 1
    record = await row(db, active)
    assert record.items is None and record.source_text is None
    assert record.confirmed_at is None
    assert record.id != old_id  # an analysis of the old file now matches nothing
    assert record.storage_key == storage_key(active.id, record.id)
    assert list(storage.files) == [record.storage_key]


async def test_an_upload_during_an_analysis_keeps_nothing_of_the_old_file(
    client, storage, db, active
):
    """No row is locked through the S3 upload, so the old file's analysis may finish
    meanwhile; the swap after the upload still leaves nothing of it (C1)."""
    await seed(db, active, MedicalRecordState.pending, items=None, text=None)
    old = await row(db, active)
    held, gate = asyncio.Event(), asyncio.Event()
    upload = storage.upload

    async def held_upload(key, data, content_type="application/octet-stream"):
        held.set()
        await gate.wait()
        await upload(key, data, content_type)

    storage.upload = held_upload
    put = asyncio.create_task(put_pdf(client, active))
    await held.wait()
    analysis = asyncio.create_task(
        analyze(
            old.id,
            storage=OldFile({old.storage_key: text_pdf([TEXT])}),
            ocr=no_ocr,
            model=model_returning(),
        )
    )
    await asyncio.wait_for(analysis, 5)  # nothing holds it up now
    assert (await row(db, active)).state is MedicalRecordState.review
    gate.set()
    assert (await put).status_code == 200
    await mark_failed(old.id)
    record = await row(db, active)
    assert record.id != old.id
    assert record.state is MedicalRecordState.pending
    assert record.items is None and record.source_text is None


async def test_das_sees_nothing_before_confirmation(
    client, storage, db, add_user, das, medic, active
):
    await seed(db, active, MedicalRecordState.review)
    body = (await get_record(client, active, DAS)).json()
    assert body["state"] == "review" and body["items"] is None
    assert body["pdf_url"] is None
    full = (await get_record(client, active)).json()
    assert len(full["items"]) == 2 and full["pdf_url"].startswith("https://s3.test/")
    await command(
        client,
        active,
        "/confirm",
        {
            "items": [
                {"included": True, "question": "a"},
                {"included": True, "question": "b"},
            ]
        },
    )
    seen = (await get_record(client, active, DAS)).json()
    assert len(seen["items"]) == 2 and seen["pdf_url"] is not None


async def test_others_get_not_found(client, storage, db, add_user, medic, senior):
    await add_user(DAS, Role.das)
    assert refusal(await get_record(client, senior, DAS)) == NOT_FOUND  # draft
    await add_user(OTHER_MEDIC, Role.medic)
    assert refusal(await get_record(client, senior, OTHER_MEDIC)) == NOT_FOUND


async def test_no_record_is_204(client, storage, senior):
    assert (await get_record(client, senior)).status_code == 204


async def test_a_storage_error_leaves_the_url_null(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    storage.down = True
    body = (await get_record(client, active)).json()
    assert body["pdf_url"] is None and body["items"] is not None


async def test_confirm_keeps_stored_fields(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    form = {
        "items": [
            {"included": True, "question": "  Ați luat insulina dimineața? "},
            {"included": False, "question": "x"},
        ]
    }
    body = (await command(client, active, "/confirm", form)).json()
    assert body["state"] == "confirmed"
    assert body["items"][0]["condition"] == STORED[0]["condition"]
    assert body["items"][0]["question"] == "Ați luat insulina dimineața?"
    assert body["items"][1]["included"] is False
    assert body["items"][1]["worrying"] == STORED[1]["worrying"]


async def test_confirm_with_other_item_count_is_refused(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    r = await command(client, active, "/confirm", {"items": []})
    assert (r.status_code, r.json()["detail"]["reason"]) == (409, "wrong_state")
    assert (await row(db, active)).state is MedicalRecordState.review


async def test_confirm_on_pending_is_refused(client, storage, db, active):
    await seed(db, active, MedicalRecordState.pending, items=None)
    r = await command(client, active, "/confirm", {"items": []})
    assert r.status_code == 409


async def test_confirm_needs_an_analyzable_senior(client, storage, db, senior):
    await seed(db, senior, MedicalRecordState.review)  # draft
    form = {"items": [{"included": True, "question": "a"}] * 2}
    assert (await command(client, senior, "/confirm", form)).status_code == 409


async def test_reanalyze_keeps_the_text(client, storage, db, active):
    await seed(db, active, MedicalRecordState.confirmed)
    r = await command(client, active, "/reanalyze")
    assert r.json()["state"] == "pending" and r.json()["items"] is None
    record = await row(db, active)
    assert record.source_text == "text" and record.confirmed_at is None
    assert (await command(client, active, "/reanalyze")).status_code == 409  # pending


async def test_confirmed_checks_reads_included_items_only(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    assert await confirmed_checks(db, active.id) == []
    await command(
        client,
        active,
        "/confirm",
        {
            "items": [
                {"included": True, "question": "q1"},
                {"included": False, "question": "q2"},
            ]
        },
    )
    assert await confirmed_checks(db, active.id) == [("q1", STORED[0]["worrying"])]


async def test_a_chunked_body_over_the_limit_is_cut_off(client, storage, senior):
    async def chunks():
        for _ in range(MAX_BYTES // 65536 + 2):
            yield b"%PDF" + b"0" * 65532

    r = await client.put(url(senior), content=chunks(), headers=signed_in(MEDIC))
    assert "content-length" not in r.request.headers
    assert (r.status_code, r.json()["detail"]["reason"]) == (413, "too_large")
    assert storage.files == {}


async def test_a_declared_length_over_the_limit_is_refused_unread(
    client, storage, senior
):
    headers = {**signed_in(MEDIC), "Content-Length": str(MAX_BYTES + 1)}
    r = await client.put(url(senior), content=b"%PDF", headers=headers)
    assert (r.status_code, r.json()["detail"]["reason"]) == (413, "too_large")


async def test_caregiver_and_senior_get_not_found(
    client, storage, db, add_user, medic, active
):
    caregiver = await add_user("+40700000305")
    db.add(
        Grant(
            user_id=caregiver.id,
            role=Role.caregiver,
            senior_id=active.id,
            granted_by=medic.id,
        )
    )
    await db.commit()
    for token in ("+40700000305", SENIOR):
        assert refusal(await get_record(client, active, token)) == NOT_FOUND


async def test_confirm_takes_an_edited_worry(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    form = {
        "items": [
            {"included": True, "question": "Ați avut amețeli?", "worrying": " Da "},
            {"included": True, "question": "q"},
        ]
    }
    body = (await command(client, active, "/confirm", form)).json()
    assert body["items"][0]["worrying"] == "Da"
    assert body["items"][1]["worrying"] == STORED[1]["worrying"]


async def test_confirm_of_an_older_profile_is_refused(client, storage, db, active):
    await seed(db, active, MedicalRecordState.review)
    form = {
        "items": [{"included": True, "question": "a"}] * 2,
        "analyzed_at": "2026-01-01T00:00:00Z",
    }
    r = await command(client, active, "/confirm", form)
    assert (r.status_code, r.json()["detail"]["reason"]) == (409, "wrong_state")
    assert (await row(db, active)).state is MedicalRecordState.review


async def test_a_draft_with_a_record_can_be_deleted(client, storage, db, senior):
    assert (await put_pdf(client, senior)).status_code == 200
    r = await client.delete(f"/api/seniors/{senior.id}", headers=signed_in(MEDIC))
    assert r.status_code == 204
    assert await row(db, senior) is None
