"""A senior's caregivers (seniors §3.4, §3.5; UC-01 step 3)."""

import asyncio
import logging
import uuid

import pytest
from sqlalchemy import select

from app.models import EnrollmentState, Grant, Role, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
LANDLINE = "+40256123456"

BODY = {"display_name": "Ioana Pop", "relation": "fiică", "phone": "0700 000 004"}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str) -> dict:
    return {"detail": {"reason": reason}}


@pytest.fixture
async def medic(add_user):
    return await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")


@pytest.fixture
async def senior(add_senior, medic):
    return await add_senior(LANDLINE, medic=medic)


async def add(client, senior_id, body=BODY, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/caregivers", json=body, headers=signed_in(token)
    )


async def remove(client, senior_id, user_id, token=MEDIC):
    return await client.delete(
        f"/api/seniors/{senior_id}/caregivers/{user_id}", headers=signed_in(token)
    )


async def me(client, token=CAREGIVER):
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
async def test_refusals(client, senior, headers, status, reason):
    path = f"/api/seniors/{senior.id}/caregivers"
    r = await client.post(path, json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))
    r = await client.delete(f"{path}/{uuid.uuid4()}", headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_add_a_caregiver(client, db, medic, senior):
    r = await add(client, senior.id)
    assert r.status_code == 201
    assert r.json() == {
        "user_id": r.json()["user_id"],
        "display_name": "Ioana Pop",
        "relation": "fiică",
        "phone_e164": CAREGIVER,
    }
    grant = await db.scalar(select(Grant).where(Grant.role == Role.caregiver))
    assert (grant.senior_id, grant.relation, grant.granted_by) == (
        senior.id,
        "fiică",
        medic.id,
    )
    page = await client.get(f"/api/seniors/{senior.id}", headers=signed_in(MEDIC))
    assert page.json()["caregivers"] == [r.json()]


async def test_the_caregiver_signs_in_and_sees_only_her(client, add_senior, senior):
    await add_senior("+40256000009", name="Someone Else")
    await add(client, senior.id)
    assert (await me(client)).json()["grants"] == [
        {
            "role": "caregiver",
            "senior_id": str(senior.id),
            "senior_form_of_address": "doamna Maria",
            "relation": "fiică",
        }
    ]
    r = await client.get("/api/seniors", headers=signed_in(CAREGIVER))
    assert [s["id"] for s in r.json()] == [str(senior.id)]


async def test_a_known_number_keeps_its_name(client, add_user, senior):
    await add_user(CAREGIVER, Role.medic, name="Dr. Ioana Pop")
    r = await add(client, senior.id)
    assert (r.status_code, r.json()["display_name"]) == (201, "Dr. Ioana Pop")


@pytest.mark.parametrize(
    "change",
    [
        {"phone": "0256 123 456"},  # a landline cannot receive the sign-in SMS
        {"phone": "12345"},
        {"relation": "   "},
        {"relation": "x" * 61},
        {"display_name": ""},
        {"display_name": "x" * 121},
        {"display_name": "Io\x00ana"},  # Postgres text cannot hold a NUL
        {"relation": "fi\x00că"},
    ],
)
async def test_invalid_bodies(client, db, senior, change):
    r = await add(client, senior.id, {**BODY, **change})
    assert r.status_code == 422
    assert await db.scalar(select(Grant).where(Grant.role == Role.caregiver)) is None


async def test_a_repeat_changes_nothing(client, db, senior):
    await add(client, senior.id)
    r = await add(client, senior.id, {**BODY, "relation": "soră"})
    assert (r.status_code, r.json()) == (409, refusal("already_done"))
    relation = select(Grant.relation).where(Grant.role == Role.caregiver)
    assert (await db.scalars(relation)).all() == ["fiică"]


async def test_two_adds_at_once(client, senior):
    first, second = await asyncio.gather(add(client, senior.id), add(client, senior.id))
    assert sorted([first.status_code, second.status_code]) == [201, 409]


async def test_a_put_and_an_add_with_the_same_new_number(client, add_senior, medic):
    # Both make a user for the number and then a grant on the senior. The PUT holds the
    # senior's row, and a plain FOR UPDATE would conflict with the key-share lock the
    # add's grant takes on it: each waits for the other (seniors §6.2).
    senior_body = {"full_name": "Maria Popescu", "form_of_address": "doamna Maria"}
    requests = []
    for n in range(8):
        senior = await add_senior(f"+4025600010{n}", medic=medic)
        mobile = f"+4070000200{n}"
        requests += [
            client.put(
                f"/api/seniors/{senior.id}",
                json={**senior_body, "phone": mobile},
                headers=signed_in(MEDIC),
            ),
            add(client, senior.id, {**BODY, "phone": mobile}),
        ]
    results = await asyncio.gather(*requests, return_exceptions=True)
    assert [getattr(r, "status_code", r) for r in results] == [200, 201] * 8


async def test_the_seniors_own_mobile_can_care(client, medic):
    # A senior who uses a relative's phone (01 §6, seniors SE12).
    made = await client.post(
        "/api/seniors",
        json={
            "full_name": "Maria Popescu",
            "form_of_address": "doamna Maria",
            "phone": CAREGIVER,
        },
        headers=signed_in(MEDIC),
    )
    senior_id = made.json()["id"]
    r = await add(client, senior_id)
    assert r.status_code == 201
    # A known limit (seniors §11): the number's user was named for the senior, and a
    # user keeps their name, so the caregiver shows under it.
    assert r.json()["display_name"] == "Maria Popescu"
    assert [g["role"] for g in (await me(client)).json()["grants"]] == [
        "caregiver",
        "senior",
    ]
    # Removing the caregiver grant leaves the senior's own.
    assert (await remove(client, senior_id, r.json()["user_id"])).status_code == 204
    assert [g["role"] for g in (await me(client)).json()["grants"]] == ["senior"]


async def test_giving_and_removing_a_caregiver_is_logged(client, medic, senior, caplog):
    caplog.set_level(logging.INFO, logger="sentinela")
    added = await add(client, senior.id)
    caregiver_id = added.json()["user_id"]
    await remove(client, senior.id, caregiver_id)
    for done in ("added", "removed"):
        line = f"caregiver {done}: user {medic.id}, senior {senior.id}, caregiver "
        assert f"{line}{caregiver_id}" in caplog.text
    # Ids only, never a number or a name (auth-layer AL15).
    assert CAREGIVER not in caplog.text
    assert BODY["display_name"] not in caplog.text


async def test_removed_caregiver_is_not_registered(client, db, senior):
    added = await add(client, senior.id)
    r = await remove(client, senior.id, added.json()["user_id"])
    assert (r.status_code, r.content) == (204, b"")
    assert ((await me(client)).status_code, (await me(client)).json()) == (
        403,
        refusal("not_registered"),
    )
    # The user row stays (seniors §3.5).
    assert await db.scalar(select(User.id).where(User.phone_e164 == CAREGIVER))
    page = await client.get(f"/api/seniors/{senior.id}", headers=signed_in(MEDIC))
    assert page.json()["caregivers"] == []


async def test_removing_keeps_their_other_grants(
    client, add_user, add_senior, medic, senior
):
    await add_user(CAREGIVER, Role.medic)
    father = await add_senior("+40256000009", name="Ion Pop", medic=medic)
    added = await add(client, senior.id)
    await add(client, father.id)
    await remove(client, senior.id, added.json()["user_id"])
    grants = (await me(client)).json()["grants"]
    assert [(g["role"], g["senior_id"]) for g in grants] == [
        ("medic", None),
        ("caregiver", str(father.id)),
    ]


async def test_removing_someone_who_is_not_her_caregiver(
    client, add_senior, medic, senior
):
    r = await remove(client, senior.id, uuid.uuid4())
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    # A caregiver of another senior is not this senior's.
    other = await add_senior("+40256000009", name="Ion Pop", medic=medic)
    added = await add(client, other.id)
    r = await remove(client, senior.id, added.json()["user_id"])
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    # And a second removal finds nothing to remove.
    await remove(client, other.id, added.json()["user_id"])
    r = await remove(client, other.id, added.json()["user_id"])
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_das_manages_caregivers_once_submitted(
    client, db, add_user, add_senior, medic, senior
):
    await add_user(DAS, Role.das)
    r = await add(client, senior.id, token=DAS)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))  # a draft
    sent = await add_senior(
        "+40256000009", medic=medic, enrollment_state=EnrollmentState.submitted
    )
    added = await add(client, sent.id, token=DAS)
    assert added.status_code == 201
    r = await remove(client, sent.id, added.json()["user_id"], token=DAS)
    assert r.status_code == 204


async def test_another_medic_is_told_not_found(client, add_user, senior):
    await add_user(OTHER_MEDIC, Role.medic)
    r = await add(client, senior.id, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    r = await remove(client, senior.id, uuid.uuid4(), token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_a_caregiver_cannot_add_or_remove(client, senior):
    added = await add(client, senior.id)
    r = await add(client, senior.id, {**BODY, "phone": "0700 000 006"}, token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    r = await remove(client, senior.id, added.json()["user_id"], token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
