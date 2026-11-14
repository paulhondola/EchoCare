"""GET /api/seniors/{id}/export (GDPR Art. 15 & 20; 04 §1, design 2026-11-14)."""

import pytest

from app.auth.models import Grant, Role
from app.core.storage import get_storage
from app.incidents.models import Incident, IncidentStatus
from app.main import app
from app.medical.models import MedicalRecord, MedicalRecordState
from app.voice.calls import CallState
from tests.export.test_service import add_call
from tests.medical.test_api import FakeStorage
from tests.seniors.test_seniors import NOT_ALLOWED, NOT_FOUND, refusal, signed_in

DAS = "+40700000001"
CAREGIVER = "+40700000201"
OTHER_MEDIC = "+40700000301"


@pytest.fixture
def storage():
    fake = FakeStorage()
    app.dependency_overrides[get_storage] = lambda: fake
    return fake


@pytest.fixture
async def senior(db, add_user, add_active_senior, storage):
    """An active senior with a confirmed medical record PDF in the store, and a caregiver."""
    await add_user(DAS, Role.das)
    await add_user(OTHER_MEDIC, Role.medic)
    senior = await add_active_senior("+40700000101")
    caregiver = await add_user(CAREGIVER, name="Ion Pop")
    key = f"medical-records/{senior.id}/r.pdf"
    storage.files[key] = b"%PDF"
    db.add_all(
        [
            MedicalRecord(
                senior_id=senior.id,
                storage_key=key,
                uploaded_by=senior.medic_id,
                state=MedicalRecordState.confirmed,
                items=[
                    {
                        "condition": "HTA",
                        "question": "Ați luat pastila?",
                        "worrying": "Nu",
                        "evidence": "HTA",
                        "included": True,
                    }
                ],
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


def export(client, senior_id, token=DAS):
    return client.get(f"/api/seniors/{senior_id}/export", headers=signed_in(token))


async def test_export_200_for_das_and_medic(client, senior, add_senior):
    r = await export(client, senior.id, DAS)
    assert r.status_code == 200
    body = r.json()
    assert body["senior"]["id"] == str(senior.id)
    assert body["medical_record"]["state"] == "confirmed"
    assert len(body["medical_record"]["items"]) == 1
    assert body["medical_record"]["pdf_url"] is not None

    draft = await add_senior("+40700000102")
    medic_phone = f"+4079{'+40700000102'[-7:]}"
    r_draft = await export(client, draft.id, medic_phone)
    assert r_draft.status_code == 200
    assert r_draft.json()["senior"]["id"] == str(draft.id)


async def test_export_succeeds_during_live_call_and_open_incident(client, db, senior):
    call = add_call(db, senior, state=CallState.ringing)
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

    r = await export(client, senior.id, DAS)
    assert r.status_code == 200
    body = r.json()
    assert len(body["calls"]) == 1
    assert body["calls"][0]["state"] == "ringing"
    assert len(body["incidents"]) == 1
    assert body["incidents"][0]["status"] == "open"


async def test_export_with_storage_down_still_200(client, senior, storage):
    storage.down = True
    r = await export(client, senior.id, DAS)
    assert r.status_code == 200
    body = r.json()
    assert body["medical_record"]["state"] == "confirmed"
    assert body["medical_record"]["pdf_url"] is None


async def test_export_refusals(client, senior, add_senior):
    draft = await add_senior("+40700000102")
    assert refusal(await export(client, draft.id, DAS)) == NOT_FOUND
    assert refusal(await export(client, senior.id, CAREGIVER)) == NOT_ALLOWED
    assert refusal(await export(client, senior.id, OTHER_MEDIC)) == NOT_FOUND
