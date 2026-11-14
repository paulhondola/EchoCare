"""Seniors, caregiver and senior grants, and who reaches whom (#16, auth-layer §3.6)."""

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, update

from app.core.db import engine
from app.models import (
    Call,
    Consent,
    EnrollmentState,
    Grant,
    Role,
    Senior,
    SeniorStatus,
    User,
)
from app.status.engine import Severity

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
SENIOR = "+40700000005"
STRANGER = "+40700000009"

MARIA = {
    "full_name": "Maria Pop",
    "form_of_address": "doamna Maria",
    "phone": "0700 000 005",
    "street": "Str. Florilor",
    "street_number": "12",
    "block": "",  # an empty form field stores nothing
    "intercom_code": "12C",
}
ANA = {"display_name": "Ana Pop", "relation": "fiica", "phone": "0700 000 004"}


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


async def add_caregiver(client, senior_id, body=ANA, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/caregivers", json=body, headers=signed_in(token)
    )


async def set_state(db, senior_id, state: EnrollmentState) -> None:
    await db.execute(
        update(Senior).where(Senior.id == senior_id).values(enrollment_state=state)
    )
    await db.commit()


async def get(client, path, token):
    return await client.get(path, headers=signed_in(token))


def refusal(r) -> tuple[int, dict]:
    return r.status_code, r.json()


NOT_FOUND = (404, {"detail": {"reason": "not_found"}})
NOT_ALLOWED = (403, {"detail": {"reason": "not_allowed"}})


async def test_the_medic_registers_a_draft(client, staff):
    maria = await register(client)
    assert maria["enrollment_state"] == "draft"
    assert maria["phone_e164"] == SENIOR
    assert maria["phone_is_landline"] is False
    assert (maria["street"], maria["block"], maria["intercom_code"]) == (
        "Str. Florilor",
        None,
        "12C",
    )
    assert maria["caregivers"] == []
    assert maria["medic"] == {"display_name": "Dr. Pop", "practice": None}
    r = await get(client, f"/api/seniors/{maria['id']}", MEDIC)
    # Only the read says whether a call is live (04 §1)
    assert r.json() == {**maria, "call_in_progress": False, "app_signed_in": False}


async def test_a_mobile_senior_signs_in_as_herself(client, staff):
    maria = await register(client)
    r = await get(client, "/api/profile", SENIOR)
    assert r.status_code == 200
    assert r.json()["grants"] == [
        {
            "role": "senior",
            "senior_id": maria["id"],
            "senior_form_of_address": "doamna Maria",
            "relation": None,
        }
    ]
    r = await get(client, "/api/seniors", SENIOR)
    assert [s["id"] for s in r.json()] == [maria["id"]]


async def test_a_landline_senior_has_no_grant(client, db, staff):
    maria = await register(client, {**MARIA, "phone": "0256 123 456"})
    assert maria["phone_is_landline"] is True
    assert await db.scalar(select(Grant).where(Grant.role == Role.senior)) is None


PHONE_TAKEN = (409, {"detail": {"reason": "phone_taken"}})


async def test_one_mobile_one_senior(client, db, staff):
    await register(client)
    r = await client.post(
        "/api/seniors",
        json={**MARIA, "full_name": "Ion Pop", "form_of_address": "domnul Ion"},
        headers=signed_in(MEDIC),
    )
    assert refusal(r) == PHONE_TAKEN
    # nothing stored
    assert await db.scalar(select(func.count()).select_from(Senior)) == 1


async def test_an_edit_to_another_seniors_mobile(client, staff):
    await register(client)
    ion = await register(
        client, {**MARIA, "full_name": "Ion Pop", "phone": "0700 000 008"}
    )
    r = await client.put(
        f"/api/seniors/{ion['id']}", json=MARIA, headers=signed_in(MEDIC)
    )
    assert refusal(r) == PHONE_TAKEN
    r = await get(client, f"/api/seniors/{ion['id']}", MEDIC)
    assert r.json()["phone_e164"] == "+40700000008"


async def test_a_shared_mobile_from_before_stays_editable(client, add_senior, staff):
    await register(client)
    # no grant, as AL7 left it
    ion = await add_senior(SENIOR, name="Ion Pop", medic=staff)
    r = await client.put(
        f"/api/seniors/{ion.id}",
        json={**MARIA, "full_name": "Ion Pop", "street": "Str. Nouă"},
        headers=signed_in(MEDIC),
    )
    assert (r.status_code, r.json()["street"]) == (200, "Str. Nouă")


async def test_a_landline_can_be_shared(client, staff):
    await register(client, {**MARIA, "phone": "0256 123 456"})
    await register(client, {**MARIA, "full_name": "Ion Pop", "phone": "0256 123 456"})


async def test_the_caregiver_story(client, staff):
    """#16's done-when, end to end."""
    maria = await register(client)
    r = await add_caregiver(client, maria["id"])
    assert r.status_code == 201
    ana = r.json()
    assert (ana["display_name"], ana["phone_e164"], ana["relation"]) == (
        "Ana Pop",
        CAREGIVER,
        "fiica",
    )

    r = await get(client, "/api/profile", CAREGIVER)
    assert r.json()["grants"] == [
        {
            "role": "caregiver",
            "senior_id": maria["id"],
            "senior_form_of_address": "doamna Maria",
            "relation": "fiica",
        }
    ]
    await register(
        client, {**MARIA, "full_name": "Alt senior", "phone": "0256 123 456"}
    )
    r = await get(client, "/api/seniors", CAREGIVER)
    assert [s["full_name"] for s in r.json()] == ["Maria Pop"]
    r = await get(client, f"/api/seniors/{maria['id']}", MEDIC)
    assert r.json()["caregivers"] == [ana]

    assert refusal(await get(client, f"/api/seniors/{maria['id']}", OTHER_MEDIC)) == (
        NOT_FOUND
    )

    r = await client.delete(
        f"/api/seniors/{maria['id']}/caregivers/{ana['user_id']}",
        headers=signed_in(MEDIC),
    )
    assert r.status_code == 204
    r = await get(client, "/api/seniors", CAREGIVER)
    assert refusal(r) == (403, {"detail": {"reason": "not_registered"}})


async def test_a_repeated_caregiver_changes_nothing(client, staff):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    r = await add_caregiver(client, maria["id"], {**ANA, "relation": "nora"})
    assert refusal(r) == (409, {"detail": {"reason": "already_done"}})
    r = await get(client, f"/api/seniors/{maria['id']}", MEDIC)
    assert [c["relation"] for c in r.json()["caregivers"]] == ["fiica"]


async def test_two_adds_at_once(client, staff):
    maria = await register(client)
    first, second = await asyncio.gather(
        add_caregiver(client, maria["id"]), add_caregiver(client, maria["id"])
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]


async def test_a_put_and_an_add_with_the_same_new_number(client, add_senior, staff):
    # Both make a user for the number and then a grant naming the senior, whose row
    # each holds meanwhile. Neither waits on the other for good (seniors §6.2).
    requests = []
    for n in range(8):
        senior = await add_senior(f"+4025600010{n}", medic=staff)
        mobile = f"+4070000200{n}"
        requests += [
            client.put(
                f"/api/seniors/{senior.id}",
                json={**MARIA, "phone": mobile},
                headers=signed_in(MEDIC),
            ),
            add_caregiver(client, senior.id, {**ANA, "phone": mobile}),
        ]
    results = await asyncio.gather(*requests, return_exceptions=True)
    assert [getattr(r, "status_code", r) for r in results] == [200, 201] * 8


async def test_removing_twice_changes_nothing(client, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    path = f"/api/seniors/{maria['id']}/caregivers/{ana['user_id']}"
    for _ in range(2):
        r = await client.delete(path, headers=signed_in(MEDIC))
        assert r.status_code == 204


async def test_a_caregiver_of_two_keeps_the_other(client, staff):
    maria = await register(client)
    ion = await register(
        client, {**MARIA, "full_name": "Ion Pop", "phone": "0256 123 456"}
    )
    ana = (await add_caregiver(client, maria["id"])).json()
    await add_caregiver(client, ion["id"])
    await client.delete(
        f"/api/seniors/{maria['id']}/caregivers/{ana['user_id']}",
        headers=signed_in(MEDIC),
    )
    r = await get(client, "/api/seniors", CAREGIVER)
    assert [s["full_name"] for s in r.json()] == ["Ion Pop"]


async def test_das_sees_a_senior_once_submitted(client, db, staff):
    maria = await register(client)
    path = f"/api/seniors/{maria['id']}"
    assert (await get(client, "/api/seniors", DAS)).json() == []
    assert refusal(await get(client, path, DAS)) == NOT_FOUND

    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await get(client, "/api/seniors", DAS)
    assert [(s["id"], s["enrollment_state"]) for s in r.json()] == [
        (maria["id"], "submitted")
    ]
    assert (await get(client, path, DAS)).status_code == 200
    # DAS edits what she reaches (SE9)
    r = await client.put(path, json=MARIA, headers=signed_in(DAS))
    assert r.status_code == 200


async def test_the_medic_edits_in_any_state(client, db, staff):
    maria = await register(client)
    path = f"/api/seniors/{maria['id']}"
    # A draft may lack the address
    r = await client.put(path, json={**MARIA, "street": ""}, headers=signed_in(MEDIC))
    assert (r.status_code, r.json()["street"]) == (200, None)

    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await client.put(
        path, json={**MARIA, "landmark": "lângă farmacie"}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 200
    assert (r.json()["landmark"], r.json()["enrollment_state"]) == (
        "lângă farmacie",
        "submitted",
    )
    # A request stays one DAS can drive to
    r = await client.put(
        path, json={**MARIA, "street_number": " "}, headers=signed_in(MEDIC)
    )
    assert refusal(r) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["street_number"]}},
    )

    await set_state(db, maria["id"], EnrollmentState.accepted)
    r = await client.put(path, json=MARIA, headers=signed_in(MEDIC))
    assert r.status_code == 200
    r = await client.put(path, json={**MARIA, "street": ""}, headers=signed_in(MEDIC))
    assert refusal(r) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["street"]}},
    )


async def test_the_last_caregiver_stays_past_draft(client, db, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    ion = (
        await add_caregiver(
            client, maria["id"], {**ANA, "display_name": "Ion", "phone": "0700 000 007"}
        )
    ).json()
    await set_state(db, maria["id"], EnrollmentState.submitted)
    base = f"/api/seniors/{maria['id']}/caregivers"
    r = await client.delete(f"{base}/{ion['user_id']}", headers=signed_in(MEDIC))
    assert r.status_code == 204
    r = await client.delete(f"{base}/{ana['user_id']}", headers=signed_in(MEDIC))
    assert refusal(r) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["caregiver"]}},
    )
    r = await get(client, f"/api/seniors/{maria['id']}", MEDIC)
    assert [c["display_name"] for c in r.json()["caregivers"]] == ["Ana Pop"]


async def test_another_medic_who_is_also_das_edits_as_das(client, db, add_user):
    # She reaches a submitted senior as DAS, so she may edit it (SE9); as a medic she
    # is not the senior's, so submit stays the registering medic's.
    await add_user(MEDIC, Role.medic, name="Dr. Pop")
    await add_user(OTHER_MEDIC, Role.medic, Role.das, name="Dr. Alt")
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    await set_state(db, maria["id"], EnrollmentState.submitted)
    path = f"/api/seniors/{maria['id']}"
    other = signed_in(OTHER_MEDIC)
    assert (await get(client, path, OTHER_MEDIC)).status_code == 200
    r = await client.put(path, json=MARIA, headers=other)
    assert r.status_code == 200
    r = await add_caregiver(
        client, maria["id"], {**ANA, "phone": "0700 000 007"}, OTHER_MEDIC
    )
    assert r.status_code == 201
    ion = r.json()
    r = await client.delete(f"{path}/caregivers/{ana['user_id']}", headers=other)
    assert r.status_code == 204
    r = await client.post(f"{path}/submit", headers=other)
    assert refusal(r) == NOT_ALLOWED
    r = await get(client, path, MEDIC)
    assert [c["user_id"] for c in r.json()["caregivers"]] == [ion["user_id"]]


async def test_das_edits_an_active_senior(client, db, staff):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    await set_state(db, maria["id"], EnrollmentState.active)
    path = f"/api/seniors/{maria['id']}"
    r = await client.put(
        path, json={**MARIA, "landmark": "lângă farmacie"}, headers=signed_in(DAS)
    )
    assert (r.status_code, r.json()["landmark"]) == (200, "lângă farmacie")
    ion = await add_caregiver(
        client,
        maria["id"],
        {**ANA, "display_name": "Ion", "phone": "0700 000 007"},
        DAS,
    )
    assert ion.status_code == 201
    r = await client.delete(
        f"{path}/caregivers/{ion.json()['user_id']}", headers=signed_in(DAS)
    )
    assert r.status_code == 204


async def test_das_does_not_reach_a_draft(client, staff):
    maria = await register(client)
    r = await client.put(
        f"/api/seniors/{maria['id']}", json=MARIA, headers=signed_in(DAS)
    )
    assert refusal(r) == NOT_FOUND


async def test_a_new_number_moves_the_senior_grant(client, db, staff):
    maria = await register(client)
    r = await client.put(
        f"/api/seniors/{maria['id']}",
        json={**MARIA, "phone": "0700 000 006"},
        headers=signed_in(MEDIC),
    )
    assert r.status_code == 200
    holders = await db.scalars(
        select(User.phone_e164)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.role == Role.senior)
    )
    assert holders.all() == ["+40700000006"]


async def test_a_das_edit_records_who_moved_the_senior_grant(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    r = await client.put(
        f"/api/seniors/{maria['id']}",
        json={**MARIA, "phone": "0700 000 006"},
        headers=signed_in(DAS),
    )
    assert r.status_code == 200
    das_id = await db.scalar(select(User.id).where(User.phone_e164 == DAS))
    granted_by = await db.scalar(
        select(Grant.granted_by)
        .join(User, User.id == Grant.user_id)
        .where(Grant.role == Role.senior, User.phone_e164 == "+40700000006")
    )
    assert granted_by == das_id


async def test_a_landline_number_drops_the_senior_grant(client, db, staff):
    maria = await register(client)
    r = await client.put(
        f"/api/seniors/{maria['id']}",
        json={**MARIA, "phone": "0256 123 456"},
        headers=signed_in(MEDIC),
    )
    assert r.json()["phone_is_landline"] is True
    assert await db.scalar(select(Grant).where(Grant.role == Role.senior)) is None


async def test_a_revoked_medic_loses_their_seniors(client, db, add_user):
    medic = await add_user(MEDIC, Role.medic, Role.das)
    maria = await register(client)
    await db.execute(
        delete(Grant).where(Grant.user_id == medic.id, Grant.role == Role.medic)
    )
    await db.commit()
    # Still DAS, and medic_id still names them, but a draft is the medic's alone
    r = await get(client, f"/api/seniors/{maria['id']}", MEDIC)
    assert refusal(r) == NOT_FOUND


@pytest.mark.parametrize("token", [OTHER_MEDIC, CAREGIVER, SENIOR])
async def test_others_cannot_change_a_senior(client, staff, token):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    path = f"/api/seniors/{maria['id']}"
    # Another medic does not reach her; her caregiver and she are not medics
    expected = NOT_FOUND if token == OTHER_MEDIC else NOT_ALLOWED
    r = await client.put(path, json=MARIA, headers=signed_in(token))
    assert refusal(r) == expected
    r = await add_caregiver(
        client, maria["id"], {**ANA, "phone": "0700 000 007"}, token
    )
    assert refusal(r) == expected
    ana = (await get(client, path, MEDIC)).json()["caregivers"][0]
    r = await client.delete(
        f"{path}/caregivers/{ana['user_id']}", headers=signed_in(token)
    )
    assert refusal(r) == expected
    r = await patch_caregiver(
        client, maria["id"], ana["user_id"], {"relation": "nora"}, token
    )
    assert refusal(r) == expected


async def patch_caregiver(client, senior_id, user_id, body, token=MEDIC, headers=None):
    return await client.patch(
        f"/api/seniors/{senior_id}/caregivers/{user_id}",
        json=body,
        headers=signed_in(token) if headers is None else headers,
    )


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in(STRANGER), 403, "not_registered"),
    ],
)
async def test_signed_out_and_unknown(client, staff, headers, status, reason):
    maria = await register(client)
    for path in ("/api/seniors", f"/api/seniors/{maria['id']}"):
        r = await client.get(path, headers=headers)
        assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    r = await patch_caregiver(client, maria["id"], staff.id, {}, headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})


async def test_das_cannot_register(client, staff):
    r = await client.post("/api/seniors", json=MARIA, headers=signed_in(DAS))
    assert refusal(r) == NOT_ALLOWED


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": "  "},
        {"form_of_address": ""},
        {"phone": "12345"},
        {"block": "x" * 21},
        {"full_name": "Ma\x00ria"},  # Postgres text cannot hold a NUL
        {"street": "Str.\x00 Florilor"},
    ],
)
async def test_invalid_registrations(client, staff, change):
    r = await client.post(
        "/api/seniors", json={**MARIA, **change}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 422


def test_database_errors_hide_their_parameters():
    # They are names, numbers and addresses (auth-layer AL15).
    assert engine.sync_engine.hide_parameters


@pytest.mark.parametrize(
    "change",
    [
        {"phone": "0256 123 456"},
        {"relation": " "},
        {"display_name": ""},
        {"display_name": "A\x00na"},
    ],
)
async def test_invalid_caregivers(client, staff, change):
    # A caregiver signs in by SMS, so their number must be a mobile.
    maria = await register(client)
    r = await add_caregiver(client, maria["id"], {**ANA, **change})
    assert r.status_code == 422


async def test_the_medic_edits_a_caregiver(client, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    r = await patch_caregiver(
        client,
        maria["id"],
        ana["user_id"],
        {"display_name": "Ana Ionescu", "relation": "nora"},
    )
    assert r.json() == {**ana, "display_name": "Ana Ionescu", "relation": "nora"}
    # everywhere (Q13)
    assert (await get(client, "/api/profile", CAREGIVER)).json()[
        "display_name"
    ] == "Ana Ionescu"


async def test_an_empty_caregiver_patch(client, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    r = await patch_caregiver(client, maria["id"], ana["user_id"], {})
    assert (r.status_code, r.json()) == (200, ana)


async def test_a_staff_caregiver_keeps_their_name(client, staff):
    maria = await register(client)
    dr = (
        await add_caregiver(client, maria["id"], {**ANA, "phone": OTHER_MEDIC})
    ).json()
    r = await patch_caregiver(client, maria["id"], dr["user_id"], {"display_name": "X"})
    assert refusal(r) == NOT_ALLOWED
    r = await patch_caregiver(client, maria["id"], dr["user_id"], {"relation": "vecin"})
    assert (r.status_code, r.json()["display_name"], r.json()["relation"]) == (
        200,
        "Dr. Alt",
        "vecin",
    )


async def test_patching_someone_who_is_not_her_caregiver(client, staff):
    maria = await register(client)
    r = await patch_caregiver(client, maria["id"], staff.id, {"relation": "x"})
    assert refusal(r) == NOT_FOUND


async def test_das_edits_a_caregiver(client, db, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await patch_caregiver(
        client, maria["id"], ana["user_id"], {"relation": "nora"}, DAS
    )
    assert r.status_code == 200


async def test_the_medic_deletes_a_draft(client, db, staff):
    maria = await register(client)
    senior_id = uuid.UUID(maria["id"])
    await add_caregiver(client, maria["id"])
    db.add(
        Consent(
            senior_id=senior_id,
            decision="given",
            method="signature",
            text_version="v1",
            signature_strokes=[[[0.1, 0.2]]],
            recorded_by=staff.id,
        )
    )
    await db.commit()
    path = f"/api/seniors/{maria['id']}"
    assert (await client.delete(path, headers=signed_in(MEDIC))).status_code == 204
    assert refusal(await get(client, path, MEDIC)) == NOT_FOUND
    assert await db.scalar(select(Grant).where(Grant.senior_id == senior_id)) is None
    assert (
        await db.scalar(select(Consent).where(Consent.senior_id == senior_id))
    ) is None
    # the person stays
    assert (
        await db.scalar(select(User).where(User.phone_e164 == CAREGIVER))
    ) is not None
    # a repeat
    assert refusal(await client.delete(path, headers=signed_in(MEDIC))) == NOT_FOUND


async def test_only_a_draft_is_deleted(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(MEDIC))
    assert refusal(r) == (409, {"detail": {"reason": "wrong_state"}})


async def test_a_draft_with_a_call_stays(client, db, staff):
    maria = await register(client)
    db.add(
        Call(
            senior_id=uuid.UUID(maria["id"]),
            trigger="test",
            starting_severity="green",
            due_at=datetime.now(UTC),
            state="completed",
        )
    )
    await db.commit()
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(MEDIC))
    assert refusal(r) == (409, {"detail": {"reason": "wrong_state"}})
    assert (await get(client, f"/api/seniors/{maria['id']}", MEDIC)).status_code == 200


@pytest.mark.parametrize("token", [OTHER_MEDIC, DAS, CAREGIVER])
async def test_others_cannot_delete(client, db, staff, token):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(token))
    assert refusal(r) == (NOT_FOUND if token == OTHER_MEDIC else NOT_ALLOWED)


async def test_the_code_shows_for_an_active_senior_only(
    client, db, add_user, add_active_senior
):
    """Q17: a withdrawn senior's old code must not read as being watched."""
    await add_user(DAS, Role.das)
    maria = await add_active_senior("+40700000101")
    ion = await add_active_senior("+40700000102")
    now = datetime.now(UTC)
    db.add_all(
        [
            SeniorStatus(
                senior_id=s.id,
                code=Severity.yellow,
                reason="Nu are căldură în casă",
                since=now,
            )
            for s in (maria, ion)
        ]
    )
    ion.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    r = await client.get("/api/seniors", headers=signed_in(DAS))
    rows = {row["id"]: row for row in r.json()}
    assert (rows[str(maria.id)]["code"], rows[str(maria.id)]["reason"]) == (
        "yellow",
        "Nu are căldură în casă",
    )
    assert (rows[str(ion.id)]["code"], rows[str(ion.id)]["since"]) == (None, None)
    page = (await client.get(f"/api/seniors/{maria.id}", headers=signed_in(DAS))).json()
    assert page["code"] == "yellow"
    page = (await client.get(f"/api/seniors/{ion.id}", headers=signed_in(DAS))).json()
    assert (page["code"], page["reason"], page["since"]) == (None, None, None)


async def test_a_senior_with_no_result_has_no_code(client, add_user, add_active_senior):
    await add_user(DAS, Role.das)
    await add_active_senior("+40700000101")
    row = (await client.get("/api/seniors", headers=signed_in(DAS))).json()[0]
    assert (row["code"], row["reason"], row["since"]) == (None, None, None)


# Equipment, declared at registration (UC-01, design 2026-11-14)

LANDLINE = "0256 123 456"


async def test_equipment_round_trips_ordered_and_deduplicated(client, staff):
    s = await register(client, {**MARIA, "equipment": ["watch", "smartphone", "watch"]})
    assert s["equipment"] == ["smartphone", "watch"]


async def test_equipment_not_sent_is_not_stated(client, staff):
    assert (await register(client))["equipment"] is None


async def test_empty_equipment_is_none_declared(client, staff):
    assert (await register(client, {**MARIA, "equipment": []}))["equipment"] == []


@pytest.mark.parametrize("equipment", [["watch"], ["home_node"], ["tablet"]])
async def test_equipment_refused(client, staff, equipment):
    r = await client.post(
        "/api/seniors", json={**MARIA, "equipment": equipment}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 422


async def test_smartphone_needs_a_mobile(client, staff):
    body = {**MARIA, "phone": LANDLINE, "equipment": ["smartphone"]}
    r = await client.post("/api/seniors", json=body, headers=signed_in(MEDIC))
    assert r.status_code == 422


@pytest.mark.parametrize("sent", [{}, {"equipment": None}])
async def test_put_without_equipment_keeps_it(client, staff, sent):
    # Old APKs leave it out; Android writes an absent optional as null (ADR-001 §2.3)
    s = await register(client, {**MARIA, "equipment": ["smartphone", "watch"]})
    r = await client.put(
        f"/api/seniors/{s['id']}", json={**MARIA, **sent}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 200, r.text
    assert r.json()["equipment"] == ["smartphone", "watch"]


async def test_put_replaces_equipment(client, staff):
    s = await register(client, {**MARIA, "equipment": ["smartphone", "watch"]})
    r = await client.put(
        f"/api/seniors/{s['id']}",
        json={**MARIA, "equipment": []},
        headers=signed_in(MEDIC),
    )
    assert r.status_code == 200, r.text
    assert r.json()["equipment"] == []


async def test_landline_edit_without_equipment_keeps_the_list(client, staff):
    s = await register(client, {**MARIA, "equipment": ["smartphone"]})
    r = await client.put(
        f"/api/seniors/{s['id']}",
        json={**MARIA, "phone": LANDLINE},
        headers=signed_in(MEDIC),
    )
    assert r.status_code == 200, r.text
    assert r.json()["equipment"] == ["smartphone"]


async def page_of(client, senior_id, token=MEDIC) -> dict:
    r = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(token))
    assert r.status_code == 200, r.text
    return r.json()


async def test_app_signed_in_after_the_senior_signs_in(client, staff):
    s = await register(client)
    assert (await page_of(client, s["id"]))["app_signed_in"] is False
    await client.get("/api/profile", headers=signed_in(SENIOR))  # sets firebase_uid
    assert (await page_of(client, s["id"]))["app_signed_in"] is True


async def test_app_signed_in_is_false_for_a_landline(client, staff):
    s = await register(client, {**MARIA, "phone": LANDLINE})
    assert (await page_of(client, s["id"]))["app_signed_in"] is False


async def test_the_senior_sees_her_own_app_signed_in(client, staff):
    s = await register(client)
    await client.get("/api/profile", headers=signed_in(SENIOR))
    # The senior on her own page sees it, as she sees her watch (UC-03)
    assert (await page_of(client, s["id"], SENIOR))["app_signed_in"] is True
