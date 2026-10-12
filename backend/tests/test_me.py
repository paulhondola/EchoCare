import logging

import pytest
from sqlalchemy import select

from app.models import Grant, Role, User

DAS = "+40700000001"
NOT_SIGNED_IN = {"detail": {"reason": "not_signed_in"}}
NOT_REGISTERED = {"detail": {"reason": "not_registered"}}
# What a das or medic grant carries besides its role (seniors §3.3).
NO_SENIOR = {"senior_id": None, "senior_form_of_address": None, "relation": None}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},  # another scheme is no token at all
        signed_in("invalid"),
        signed_in("no-phone"),
    ],
)
async def test_not_signed_in(client, headers):
    r = await client.get("/api/me", headers=headers)
    assert (r.status_code, r.json()) == (401, NOT_SIGNED_IN)
    assert r.headers["www-authenticate"] == "Bearer"


async def test_unknown_number(client, caplog):
    caplog.set_level(logging.INFO, logger="sentinela.auth")
    r = await client.get("/api/me", headers=signed_in("+40700000009"))
    assert (r.status_code, r.json()) == (403, NOT_REGISTERED)
    assert "+40700***009" in caplog.text
    assert "+40700000009" not in caplog.text  # the number, and here the token too


async def test_zero_grants(client, add_user):
    await add_user(DAS)  # a user whose grants were all revoked
    r = await client.get("/api/me", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (403, NOT_REGISTERED)


async def test_grants_in_role_order(client, add_user):
    await add_user("+40700000003", Role.medic, Role.das, name="Ana Pop")
    r = await client.get("/api/me", headers=signed_in("+40700000003"))
    assert r.status_code == 200
    assert r.json() == {
        "display_name": "Ana Pop",
        "phone_e164": "+40700000003",
        "grants": [
            {"role": "das", **NO_SENIOR},
            {"role": "medic", **NO_SENIOR},
        ],
    }


async def test_one_entry_per_caregiver_grant(client, db, add_user, add_senior):
    user = await add_user("+40700000004")
    mother = (await add_senior("+40700000101")).id
    father = await add_senior("+40700000102", name="Ion Pop")
    father.form_of_address = "domnul Ion"
    db.add_all(
        [
            Grant(
                user_id=user.id, role=Role.caregiver, senior_id=mother, relation="fiică"
            ),
            Grant(
                user_id=user.id,
                role=Role.caregiver,
                senior_id=father.id,
                relation="vecină",
            ),
        ]
    )
    await db.commit()
    r = await client.get("/api/me", headers=signed_in("+40700000004"))
    grants = r.json()["grants"]
    assert [g["role"] for g in grants] == ["caregiver", "caregiver"]
    # Each names its own senior and its own relation (seniors §3.3).
    assert {
        g["senior_id"]: (g["senior_form_of_address"], g["relation"]) for g in grants
    } == {
        str(mother): ("doamna Maria", "fiică"),
        str(father.id): ("domnul Ion", "vecină"),
    }


async def test_firebase_uid_written_kept_and_replaced(client, db, add_user, caplog):
    caplog.set_level(logging.WARNING, logger="sentinela.auth")
    await add_user(DAS, Role.das)
    stored = select(User.firebase_uid).where(User.phone_e164 == DAS)

    await client.get("/api/me", headers=signed_in(DAS))
    assert await db.scalar(stored) == f"uid-{DAS}"

    await client.get("/api/me", headers=signed_in(DAS))
    assert "firebase_uid changed" not in caplog.text

    await client.get("/api/me", headers=signed_in(f"{DAS}|new-uid"))
    assert await db.scalar(stored) == "new-uid"
    assert "firebase_uid changed" in caplog.text
