"""Withdrawn consent and the signature (Q15, Q16, 04 §2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models import Call, CallTrigger, Consent, EnrollmentState, Role, Senior
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.dialogue import SIGNATURE_CONSENT_TEXT, SIGNATURE_CONSENT_VERSION

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
STRANGER = "+40700000009"

MARIA = {
    "full_name": "Maria Pop",
    "form_of_address": "doamna Maria",
    "phone": "0700 000 005",
    "street": "Str. Florilor",
    "street_number": "12",
}
ANA = {"display_name": "Ana Pop", "relation": "fiica", "phone": "0700 000 004"}

NOT_ALLOWED = (403, {"detail": {"reason": "not_allowed"}})
WRONG_STATE = (409, {"detail": {"reason": "wrong_state"}})
STROKES = [[[0.1, 0.2], [0.3, 0.4]]]


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def staff(add_user):
    await add_user(DAS, Role.das, name="DAS Test")
    await add_user(OTHER_MEDIC, Role.medic, name="Dr. Alt")
    return await add_user(MEDIC, Role.medic, name="Dr. Pop")


async def register(client, body=MARIA, token=MEDIC) -> dict:
    r = await client.post("/api/seniors", json=body, headers=signed_in(token))
    assert r.status_code == 201, r.text
    return r.json()


async def set_state(db, senior_id, state: EnrollmentState) -> None:
    await db.execute(
        update(Senior).where(Senior.id == senior_id).values(enrollment_state=state)
    )
    await db.commit()


def refusal(r) -> tuple[int, dict]:
    return r.status_code, r.json()


def withdraw(client, senior_id, token=MEDIC):
    return client.post(
        f"/api/seniors/{senior_id}/consent-withdrawn", headers=signed_in(token)
    )


def sign(client, senior_id, body=None, token=MEDIC, headers=None):
    return client.post(
        f"/api/seniors/{senior_id}/signature",
        json={"text_version": "v1", "strokes": STROKES} if body is None else body,
        headers=signed_in(token) if headers is None else headers,
    )


async def consents(db, senior_id) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(Consent)
        .where(Consent.senior_id == uuid.UUID(senior_id))
    )


async def test_the_medic_records_a_withdrawal(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    db.add(
        Consent(
            senior_id=uuid.UUID(maria["id"]),
            decision="given",
            method="call",
            text_version="v1",
        )
    )
    await db.commit()
    r = await withdraw(client, maria["id"])
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "withdrawn")
    latest = await db.scalar(
        select(Consent)
        .where(Consent.senior_id == uuid.UUID(maria["id"]))
        .order_by(Consent.at.desc())
        .limit(1)
    )
    assert (
        latest.decision,
        latest.method,
        latest.text_version,
        latest.recorded_by,
    ) == ("withdrawn", "medic", "v1", staff.id)
    r = await withdraw(client, maria["id"])
    assert refusal(r) == (409, {"detail": {"reason": "already_done"}})


async def test_das_records_a_withdrawal(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    r = await withdraw(client, maria["id"], DAS)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "withdrawn")
    row = await db.scalar(
        select(Consent).where(Consent.senior_id == uuid.UUID(maria["id"]))
    )
    assert (row.decision, row.method, row.text_version) == (
        "withdrawn",
        "das",
        "none",
    )


async def test_a_withdrawal_needs_an_active_senior(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await withdraw(client, maria["id"])
    assert refusal(r) == WRONG_STATE
    assert await consents(db, maria["id"]) == 0


async def queue_campaign_call(db, senior_id) -> uuid.UUID:
    call = Call(
        senior_id=uuid.UUID(senior_id),
        trigger=CallTrigger.campaign,
        starting_severity=Severity.green,
        due_at=datetime.now(UTC),
    )
    db.add(call)
    await db.commit()
    return call.id


async def test_withdrawal_cancels_queued_calls(client, db, staff):  # UC-04, 04 §2
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    call_id = await queue_campaign_call(db, maria["id"])
    assert (await withdraw(client, maria["id"])).status_code == 200
    state, ended_at = (
        await db.execute(select(Call.state, Call.ended_at).where(Call.id == call_id))
    ).one()
    assert (state, ended_at is not None) == (CallState.canceled, True)


async def test_a_refused_withdrawal_cancels_nothing(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    call_id = await queue_campaign_call(db, maria["id"])
    assert refusal(await withdraw(client, maria["id"])) == WRONG_STATE
    state = await db.scalar(select(Call.state).where(Call.id == call_id))
    assert state == CallState.queued


async def test_a_caregiver_cannot_withdraw(client, db, staff):
    maria = await register(client)
    await client.post(
        f"/api/seniors/{maria['id']}/caregivers", json=ANA, headers=signed_in(MEDIC)
    )
    await set_state(db, maria["id"], EnrollmentState.active)
    r = await withdraw(client, maria["id"], CAREGIVER)
    assert refusal(r) == NOT_ALLOWED


async def test_the_medic_saves_a_signature(client, db, staff):
    maria = await register(client)
    r = await sign(client, maria["id"])
    assert r.status_code == 204
    row = await db.scalar(
        select(Consent).where(Consent.senior_id == uuid.UUID(maria["id"]))
    )
    assert (row.decision, row.method, row.signature_strokes, row.recorded_by) == (
        "given",
        "signature",
        STROKES,
        staff.id,
    )


async def test_no_signature_once_active(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    r = await sign(client, maria["id"])
    assert refusal(r) == WRONG_STATE
    assert await consents(db, maria["id"]) == 0


@pytest.mark.parametrize(
    "strokes",
    [
        [],
        [[]],
        [[[1.5, 0.2]]],
        [[[0.1]]],  # a point that is not a pair (Review Focus 4)
        [[[0.1, 0.2, 0.3]]],
        [[[0.5, 0.5]] * 5001],
    ],
)
async def test_invalid_signatures(client, db, staff, strokes):
    maria = await register(client)
    r = await sign(client, maria["id"], {"text_version": "v1", "strokes": strokes})
    assert r.status_code == 422
    assert await consents(db, maria["id"]) == 0


async def test_das_cannot_sign(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await sign(client, maria["id"], token=DAS)
    assert refusal(r) == NOT_ALLOWED


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in(STRANGER), 403, "not_registered"),
    ],
)
async def test_signed_out_and_unknown(client, staff, headers, status, reason):
    maria = await register(client)
    r = await client.post(
        f"/api/seniors/{maria['id']}/consent-withdrawn", headers=headers
    )
    assert refusal(r) == (status, {"detail": {"reason": reason}})
    assert r.headers.get("www-authenticate") == ("Bearer" if status == 401 else None)
    r = await sign(client, maria["id"], headers=headers)
    assert refusal(r) == (status, {"detail": {"reason": reason}})
    assert r.headers.get("www-authenticate") == ("Bearer" if status == 401 else None)


T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def record(senior_id, decision, method, at):
    return Consent(
        senior_id=uuid.UUID(senior_id),
        decision=decision,
        method=method,
        text_version="v1",
        at=at,
    )


def page(client, senior_id, token=MEDIC):
    return client.get(f"/api/seniors/{senior_id}", headers=signed_in(token))


async def test_a_signature_is_not_the_consent(client, db, staff):  # G7, 04 §1
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    assert (await sign(client, maria["id"])).status_code == 204
    body = (await page(client, maria["id"])).json()
    assert body["consent"] is None
    assert body["consent_given_at"] is None
    assert body["signed_at"] is not None


async def test_the_consent_is_the_latest_decision_off_the_call(client, db, staff):
    maria = await register(client)
    db.add(record(maria["id"], "given", "call", T0))
    db.add(record(maria["id"], "given", "signature", T0 + timedelta(hours=1)))
    await db.commit()
    body = (await page(client, maria["id"])).json()
    assert body["consent"] == {
        "decision": "given",
        "method": "call",
        "at": "2026-11-01T09:00:00Z",
    }
    assert body["signed_at"] == "2026-11-01T10:00:00Z"


async def test_a_withdrawal_keeps_when_consent_was_given(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    db.add(record(maria["id"], "given", "app", T0))
    await db.commit()
    assert (await withdraw(client, maria["id"])).status_code == 200
    body = (await page(client, maria["id"])).json()
    assert body["consent"]["decision"] == "withdrawn"
    assert body["consent"]["method"] == "medic"
    assert body["consent_given_at"] == "2026-11-01T09:00:00Z"


async def test_a_refusal_is_the_consent(client, db, staff):
    maria = await register(client)
    db.add(record(maria["id"], "refused", "call", T0))
    await db.commit()
    body = (await page(client, maria["id"])).json()
    assert body["consent"]["decision"] == "refused"
    assert body["consent_given_at"] is None


def test_the_signature_text():
    assert SIGNATURE_CONSENT_VERSION == "v1-semnatura"
    assert SIGNATURE_CONSENT_TEXT == (
        "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva "
        "neobișnuit. Ce spuneți în apel văd medicul de familie, familia și DAS. "
        "Puteți renunța oricând. Semnând mai jos, sunteți de acord."
    )
