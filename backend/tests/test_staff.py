import asyncio

import pytest
from sqlalchemy import select

from app.models import Grant, Role, User

DAS = "+40700000001"
MEDIC = {
    "display_name": "Dr. Ion Pop",
    "phone": "0700 000 002",
    "role": "medic",
    "practice": "CMI Dr. Pop",
}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


async def post(client, body, token=DAS):
    return await client.post("/api/staff", json=body, headers=signed_in(token))


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_refusals(client, das, headers, status, reason):
    r = await client.post("/api/staff", json=MEDIC, headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"


async def test_a_medic_cannot_grant(client, add_user):
    await add_user("+40700000003", Role.medic)
    r = await post(client, MEDIC, token="+40700000003")
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})


async def test_grant_a_new_medic(client, db, das):
    r = await post(client, MEDIC)
    assert r.status_code == 201
    assert r.json() == {
        "display_name": "Dr. Ion Pop",
        "phone_e164": "+40700000002",
        "role": "medic",
        "practice": "CMI Dr. Pop",
    }
    granted_by = await db.scalar(
        select(Grant.granted_by)
        .join(User, Grant.user_id == User.id)
        .where(User.phone_e164 == "+40700000002")
    )
    assert granted_by == das.id


async def test_the_new_medic_signs_in(client, das):
    # Typed as "0700 000 002", reported by Firebase as +40700000002: one user.
    await post(client, MEDIC)
    r = await client.get("/api/me", headers=signed_in("+40700000002"))
    assert r.status_code == 200
    assert r.json()["grants"] == [{"role": "medic", "senior_id": None}]


async def test_a_known_number_keeps_its_name(client, add_user, das):
    await add_user("+40700000002", Role.das, name="Ion Pop")
    r = await post(client, MEDIC)
    assert r.status_code == 201
    assert (r.json()["display_name"], r.json()["practice"]) == (
        "Ion Pop",
        "CMI Dr. Pop",
    )


async def test_a_repeated_grant_changes_nothing(client, db, das):
    await post(client, MEDIC)
    r = await post(client, {**MEDIC, "practice": "Alt cabinet"})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "already_done"}})
    practice = select(User.practice).where(User.phone_e164 == "+40700000002")
    assert await db.scalar(practice) == "CMI Dr. Pop"


async def test_a_das_grant_keeps_the_practice(client, das):
    await post(client, MEDIC)
    r = await post(client, {**MEDIC, "role": "das", "practice": "Alt cabinet"})
    assert r.status_code == 201
    assert r.json()["practice"] == "CMI Dr. Pop"


@pytest.mark.parametrize("practice", ["", "   ", "x" * 201])
async def test_a_das_grant_ignores_any_practice(client, das, practice):
    # Ignored for das (§3.4): a form's empty practice field must not refuse the grant.
    r = await post(client, {**MEDIC, "role": "das", "practice": practice})
    assert r.status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"practice": None},  # a medic needs a practice
        {"practice": "   "},
        {"phone": "0256 123 456"},  # a landline cannot receive the sign-in SMS
        {"phone": "12345"},
        {"role": "caregiver"},  # medics grant caregivers, with a senior
        {"display_name": "   "},
    ],
)
async def test_invalid_bodies(client, das, change):
    r = await post(client, {**MEDIC, **change})
    assert r.status_code == 422


async def test_two_grants_at_once(client, das):
    first, second = await asyncio.gather(post(client, MEDIC), post(client, MEDIC))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
