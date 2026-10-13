"""Seniors, caregiver and senior grants, and who reaches whom (#16, auth-layer §3.6)."""

import asyncio

import pytest
from sqlalchemy import delete, select, update

from app.core.db import engine
from app.models import EnrollmentState, Grant, Role, Senior, User

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
    assert r.json() == maria


async def test_a_mobile_senior_signs_in_as_herself(client, staff):
    maria = await register(client)
    r = await get(client, "/api/me", SENIOR)
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


async def test_a_couple_sharing_a_mobile(client, db, staff):
    # The second senior gets no app role and still receives every call (AL7).
    first = await register(client)
    await register(
        client, {**MARIA, "full_name": "Ion Pop", "form_of_address": "domnul Ion"}
    )
    grants = (await db.scalars(select(Grant).where(Grant.role == Role.senior))).all()
    assert [str(g.senior_id) for g in grants] == [first["id"]]


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

    r = await get(client, "/api/me", CAREGIVER)
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
    # Reached, but DAS is not a medic
    r = await client.put(path, json=MARIA, headers=signed_in(DAS))
    assert refusal(r) == NOT_ALLOWED


async def test_the_medic_edits_a_draft_or_a_request(client, db, staff):
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
    assert refusal(r) == (409, {"detail": {"reason": "wrong_state"}})


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


async def test_another_medic_who_is_also_das(client, db, add_user):
    # She reaches a submitted senior as DAS; as a medic she is not the senior's.
    await add_user(MEDIC, Role.medic, name="Dr. Pop")
    await add_user(OTHER_MEDIC, Role.medic, Role.das, name="Dr. Alt")
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    await set_state(db, maria["id"], EnrollmentState.submitted)
    path = f"/api/seniors/{maria['id']}"
    other = signed_in(OTHER_MEDIC)
    assert (await get(client, path, OTHER_MEDIC)).status_code == 200
    for r in [
        await client.put(path, json=MARIA, headers=other),
        await add_caregiver(
            client, maria["id"], {**ANA, "phone": "0700 000 007"}, OTHER_MEDIC
        ),
        await client.delete(f"{path}/caregivers/{ana['user_id']}", headers=other),
        await client.post(f"{path}/submit", headers=other),
    ]:
        assert refusal(r) == NOT_ALLOWED
    r = await get(client, path, MEDIC)
    assert [c["user_id"] for c in r.json()["caregivers"]] == [ana["user_id"]]


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
