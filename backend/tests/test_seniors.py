"""Registering and editing a senior (seniors §3.4, §3.5; UC-01)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.db import engine
from app.models import EnrollmentState, Grant, Role, Senior, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
MOBILE = "+40700000005"
OTHER_MOBILE = "+40700000006"
LANDLINE = "+40256123456"

BODY = {
    "full_name": "Maria Popescu",
    "form_of_address": "doamna Maria",
    "phone": "0256 123 456",
}
ADDRESS = {"street": "Str. Daliei", "street_number": "12"}
SUBMITTED = {"enrollment_state": EnrollmentState.submitted, **ADDRESS}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str, **extra) -> dict:
    return {"detail": {"reason": reason, **extra}}


@pytest.fixture
async def medic(db, add_user):
    user = await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")
    user.practice = "CMI Dr. Pop"
    await db.commit()
    return user


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


async def create(client, body=BODY, token=MEDIC):
    return await client.post("/api/seniors", json=body, headers=signed_in(token))


async def put(client, senior_id, body, token=MEDIC):
    return await client.put(
        f"/api/seniors/{senior_id}", json=body, headers=signed_in(token)
    )


async def me(client, token):
    return await client.get("/api/me", headers=signed_in(token))


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_refusals(client, medic, headers, status, reason):
    r = await client.post("/api/seniors", json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))
    r = await client.put(f"/api/seniors/{uuid.uuid4()}", json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_only_a_medic_registers(client, das):
    r = await create(client, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_a_role_refusal_comes_before_the_body(client, das):
    # seniors §3.1: identity, role, body, reach, state.
    r = await create(client, body={}, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_a_bad_body_comes_before_reach(client, medic):
    r = await put(client, uuid.uuid4(), {})
    assert r.status_code == 422


async def test_a_draft_needs_three_fields(client, medic):
    r = await create(client)
    assert r.status_code == 201
    page = r.json()
    assert page == {
        "id": page["id"],
        "full_name": "Maria Popescu",
        "form_of_address": "doamna Maria",
        "phone_e164": LANDLINE,
        "phone_is_landline": True,
        "enrollment_state": "draft",
        "street": None,
        "street_number": None,
        "block": None,
        "staircase": None,
        "floor": None,
        "apartment": None,
        "intercom_code": None,
        "key_holder": None,
        "landmark": None,
        "call_window": None,
        "medic": {"display_name": "Dr. Ion Pop", "practice": "CMI Dr. Pop"},
        "caregivers": [],
    }
    read = await client.get(f"/api/seniors/{page['id']}", headers=signed_in(MEDIC))
    assert read.json() == page


async def test_a_landline_signs_nobody_in(client, db, medic):
    assert (await create(client)).status_code == 201
    users = select(func.count()).select_from(User).where(User.phone_e164 == LANDLINE)
    assert await db.scalar(users) == 0
    assert await db.scalar(select(func.count()).select_from(Grant)) == 1  # the medic's


async def test_a_mobile_makes_the_senior_grant(client, db, medic):
    r = await create(client, {**BODY, "phone": "0700 000 005"})
    assert (r.status_code, r.json()["phone_is_landline"]) == (201, False)
    signed = await me(client, MOBILE)
    assert signed.json() == {
        "display_name": "Maria Popescu",
        "phone_e164": MOBILE,
        "grants": [
            {
                "role": "senior",
                "senior_id": r.json()["id"],
                "senior_form_of_address": "doamna Maria",
                "relation": None,
            }
        ],
    }
    granted_by = select(Grant.granted_by).where(Grant.role == Role.senior)
    assert await db.scalar(granted_by) == medic.id


async def test_a_long_name_is_cut_for_the_user(client, db, medic):
    # seniors.full_name holds 200 characters, users.display_name 120.
    r = await create(client, {**BODY, "full_name": "A" * 150, "phone": MOBILE})
    assert (r.status_code, len(r.json()["full_name"])) == (201, 150)
    name = select(User.display_name).where(User.phone_e164 == MOBILE)
    assert await db.scalar(name) == "A" * 120


async def test_a_known_number_keeps_its_name(client, add_user, medic):
    await add_user(MOBILE, Role.medic, name="Dr. Maria Popescu")
    await create(client, {**BODY, "phone": MOBILE})
    signed = (await me(client, MOBILE)).json()
    assert signed["display_name"] == "Dr. Maria Popescu"
    assert [g["role"] for g in signed["grants"]] == ["medic", "senior"]


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": "   "},
        {"full_name": "x" * 201},
        {"full_name": "Ma\x00ria"},  # Postgres text cannot hold a NUL
        {"form_of_address": ""},
        {"form_of_address": "x" * 121},
        {"phone": "12345"},
        {"phone": None},
        {"street": "x" * 201},
        {"street": "Str.\x00 Daliei"},
        {"street_number": "x" * 21},
        {"intercom_code": "x" * 41},
        {"call_window": "x" * 61},
    ],
)
async def test_invalid_bodies(client, db, medic, change):
    r = await create(client, {**BODY, **change})
    assert r.status_code == 422
    assert await db.scalar(select(func.count()).select_from(Senior)) == 0


def test_database_errors_hide_their_parameters():
    # A failed statement must not put a name or a number in the log (auth-layer AL15).
    assert engine.sync_engine.hide_parameters


async def test_optional_fields_are_trimmed_and_a_blank_is_null(client, medic):
    r = await create(
        client, {**BODY, "street": "  Str. Daliei ", "block": "   ", "landmark": ""}
    )
    page = r.json()
    assert (page["street"], page["block"], page["landmark"]) == (
        "Str. Daliei",
        None,
        None,
    )


async def test_another_seniors_mobile_is_taken(client, db, medic):
    await create(client, {**BODY, "phone": MOBILE})
    r = await create(client, {**BODY, "full_name": "Ion Popescu", "phone": MOBILE})
    assert (r.status_code, r.json()) == (409, refusal("phone_taken"))
    assert await db.scalar(select(func.count()).select_from(Senior)) == 1


async def test_two_seniors_share_a_landline(client, db, medic):
    first = await create(client)
    second = await create(client, {**BODY, "full_name": "Ion Popescu"})
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]


async def test_put_replaces_every_field(client, medic):
    made = await create(client, {**BODY, **ADDRESS, "landmark": "lângă farmacie"})
    r = await put(client, made.json()["id"], {**BODY, "full_name": "Maria Pop"})
    page = r.json()
    assert r.status_code == 200
    assert (page["full_name"], page["street"], page["landmark"]) == (
        "Maria Pop",
        None,
        None,
    )


async def test_put_moves_the_grant_with_the_number(client, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    r = await put(client, made.json()["id"], {**BODY, "phone": OTHER_MOBILE})
    assert (r.status_code, r.json()["phone_e164"]) == (200, OTHER_MOBILE)
    assert (await me(client, MOBILE)).json() == refusal("not_registered")
    assert [g["role"] for g in (await me(client, OTHER_MOBILE)).json()["grants"]] == [
        "senior"
    ]


async def test_put_to_a_landline_removes_the_grant(client, db, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    r = await put(client, made.json()["id"], BODY)
    assert (r.status_code, r.json()["phone_is_landline"]) == (200, True)
    assert (await me(client, MOBILE)).json() == refusal("not_registered")


async def test_put_from_a_landline_makes_the_grant(client, medic):
    made = await create(client)
    await put(client, made.json()["id"], {**BODY, "phone": MOBILE})
    assert (await me(client, MOBILE)).json()["grants"][0]["role"] == "senior"


async def test_put_with_the_same_number_keeps_the_grant(client, db, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    grant = select(Grant.id).where(Grant.role == Role.senior)
    before = await db.scalar(grant)
    r = await put(
        client, made.json()["id"], {**BODY, "phone": "0700 000 005", **ADDRESS}
    )
    assert r.status_code == 200
    assert await db.scalar(grant) == before


async def test_put_to_a_taken_number_changes_nothing(client, medic):
    await create(client, {**BODY, "phone": MOBILE})
    made = await create(
        client, {**BODY, "full_name": "Ion Popescu", "phone": OTHER_MOBILE}
    )
    senior_id = made.json()["id"]
    r = await put(client, senior_id, {**BODY, "full_name": "Changed", "phone": MOBILE})
    assert (r.status_code, r.json()) == (409, refusal("phone_taken"))
    read = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(MEDIC))
    assert (read.json()["full_name"], read.json()["phone_e164"]) == (
        "Ion Popescu",
        OTHER_MOBILE,
    )
    assert (await me(client, OTHER_MOBILE)).json()["grants"][0][
        "senior_id"
    ] == senior_id


async def test_das_edits_a_submitted_senior(client, add_senior, medic, das):
    senior = await add_senior(LANDLINE, medic=medic, **SUBMITTED)
    r = await put(client, senior.id, {**BODY, **ADDRESS, "floor": "2"}, token=DAS)
    assert (r.status_code, r.json()["floor"]) == (200, "2")
    assert r.json()["enrollment_state"] == "submitted"


async def test_das_does_not_reach_a_draft(client, add_senior, medic, das):
    senior = await add_senior(LANDLINE, medic=medic)
    r = await put(client, senior.id, BODY, token=DAS)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ({**BODY, "street_number": "12"}, ["street"]),
        ({**BODY, "street": "Str. Daliei", "street_number": "  "}, ["street_number"]),
        (BODY, ["street", "street_number"]),
    ],
)
async def test_past_draft_the_address_stays(
    client, db, add_senior, medic, body, missing
):
    senior = await add_senior(LANDLINE, medic=medic, **SUBMITTED)
    r = await put(client, senior.id, body)
    assert (r.status_code, r.json()) == (422, refusal("missing_fields", fields=missing))
    await db.refresh(senior)
    assert (senior.street, senior.street_number) == ("Str. Daliei", "12")


async def test_a_draft_may_lose_its_address(client, add_senior, medic):
    senior = await add_senior(LANDLINE, medic=medic, **ADDRESS)
    r = await put(client, senior.id, BODY)
    assert (r.status_code, r.json()["street"]) == (200, None)


async def test_another_medic_is_told_not_found(client, add_user, add_senior, medic):
    await add_user(OTHER_MEDIC, Role.medic)
    senior = await add_senior(LANDLINE, medic=medic)
    r = await put(client, senior.id, BODY, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_a_caregiver_cannot_edit(client, db, add_user, add_senior, medic):
    senior = await add_senior(LANDLINE, medic=medic)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    await db.commit()
    r = await put(client, senior.id, BODY, token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
