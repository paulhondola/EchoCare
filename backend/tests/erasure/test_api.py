"""POST /api/seniors/{id}/erase, and the PDF a deleted draft leaves (design 2026-11-14)."""

import logging

import pytest

from app.auth.models import Grant, Role
from app.core.storage import get_storage
from app.incidents.models import Incident, IncidentStatus
from app.main import app
from app.medical.models import MedicalRecord
from app.voice.calls import CallState
from tests.erasure.test_service import add_call
from tests.medical.test_api import FakeStorage
from tests.seniors.test_seniors import NOT_ALLOWED, NOT_FOUND, refusal, signed_in

DAS = "+40700000001"
CAREGIVER = "+40700000201"


@pytest.fixture
def storage():
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    return fake


@pytest.fixture
async def senior(db, add_user, add_active_senior, storage):
    """An active senior with a medical record PDF in the store, and a caregiver."""
    await add_user(DAS, Role.das)
    senior = await add_active_senior("+40700000101")
    caregiver = await add_user(CAREGIVER, name="Ion Pop")
    key = f"medical-records/{senior.id}/r.pdf"
    storage.files[key] = b"%PDF"
    db.add_all(
        [
            MedicalRecord(
                senior_id=senior.id, storage_key=key, uploaded_by=senior.medic_id
            ),
            Grant(
                user_id=caregiver.id,
                role=Role.caregiver,
                senior_id=senior.id,
                granted_by=senior.medic_id,
            ),
        ]
    )
    await db.commit()
    return senior


def erase(client, senior_id, token=DAS):
    return client.post(f"/api/seniors/{senior_id}/erase", headers=signed_in(token))


async def test_erase_answers_204_and_deletes_pdf(client, senior, storage):
    assert (await erase(client, senior.id)).status_code == 204
    assert storage.files == {}
    r = await client.get(f"/api/seniors/{senior.id}", headers=signed_in(DAS))
    assert refusal(r) == NOT_FOUND


async def test_erase_twice_is_not_found(client, senior):
    assert (await erase(client, senior.id)).status_code == 204
    assert refusal(await erase(client, senior.id)) == NOT_FOUND


async def test_erase_with_storage_down_still_204(client, senior, storage, caplog):
    storage.down = True
    with caplog.at_level(logging.WARNING, logger="echocare.medical"):
        assert (await erase(client, senior.id)).status_code == 204
    assert str(senior.id) in caplog.text
    assert f"medical-records/{senior.id}/r.pdf" in caplog.text
    storage.down = False
    assert refusal(await erase(client, senior.id)) == NOT_FOUND


async def test_erase_refused_during_live_call(client, db, senior):
    add_call(db, senior, state=CallState.in_progress)
    await db.commit()
    assert refusal(await erase(client, senior.id)) == (
        409,
        {"detail": {"reason": "call_live"}},
    )


async def test_erase_refused_with_open_incident(client, db, senior):
    call = add_call(db, senior)
    await db.flush()
    db.add(
        Incident(
            senior_id=senior.id,
            status=IncidentStatus.open,
            reason="r",
            opened_by_call_id=call.id,
        )
    )
    await db.commit()
    assert refusal(await erase(client, senior.id)) == (
        409,
        {"detail": {"reason": "incident_open"}},
    )


async def test_caregiver_cannot_erase(client, senior):
    """A caregiver reaches the senior (01 §6) but may not edit them: 403."""
    assert refusal(await erase(client, senior.id, CAREGIVER)) == NOT_ALLOWED


async def test_delete_draft_deletes_pdf(client, db, add_senior, storage):
    draft = await add_senior("+40700000101")
    medic_phone = f"+4079{'+40700000101'[-7:]}"
    key = f"medical-records/{draft.id}/r.pdf"
    storage.files[key] = b"%PDF"
    db.add(
        MedicalRecord(senior_id=draft.id, storage_key=key, uploaded_by=draft.medic_id)
    )
    await db.commit()
    r = await client.delete(f"/api/seniors/{draft.id}", headers=signed_in(medic_phone))
    assert r.status_code == 204
    assert storage.files == {}


async def test_delete_draft_with_storage_down_still_204(
    client, db, add_senior, storage
):
    draft = await add_senior("+40700000101")
    medic_phone = f"+4079{'+40700000101'[-7:]}"
    db.add(
        MedicalRecord(
            senior_id=draft.id,
            storage_key=f"medical-records/{draft.id}/r.pdf",
            uploaded_by=draft.medic_id,
        )
    )
    await db.commit()
    storage.down = True
    r = await client.delete(f"/api/seniors/{draft.id}", headers=signed_in(medic_phone))
    assert r.status_code == 204
