import asyncio
import uuid

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
    r = await client.get("/api/profile", headers=signed_in("+40700000002"))
    assert r.status_code == 200
    assert [(g["role"], g["senior_id"]) for g in r.json()["grants"]] == [
        ("medic", None)
    ]


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


async def test_the_staff_list(client, db, add_user, add_senior, das):
    await add_user("+40700000003", Role.medic, Role.das, name="Ana Ionescu")
    senior = await add_senior("+40700000101")  # also adds its medic, "Medic"
    caregiver = await add_user("+40700000004", name="Ion Pop")
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    await db.commit()

    r = await client.get("/api/staff", headers=signed_in(DAS))
    assert r.status_code == 200
    staff = [(s["display_name"], s["phone_e164"], s["roles"]) for s in r.json()]
    # By name, once per person, das before medic; caregivers are not staff.
    assert staff == [
        ("Ana Ionescu", "+40700000003", ["das", "medic"]),
        ("DAS Test", DAS, ["das"]),
        ("Medic", "+40790000101", ["medic"]),
    ]
    assert r.json()[1] == {
        "id": str(das.id),
        "display_name": "DAS Test",
        "phone_e164": DAS,
        "practice": None,
        "roles": ["das"],
        "on_duty": False,
    }


async def test_a_granted_medic_is_listed(client, das):
    await post(client, MEDIC)
    r = await client.get("/api/staff", headers=signed_in(DAS))
    medic = next(s for s in r.json() if s["phone_e164"] == "+40700000002")
    assert (medic["roles"], medic["practice"]) == (["medic"], "CMI Dr. Pop")


@pytest.mark.parametrize(
    ("token", "status", "reason"),
    [
        (None, 401, "not_signed_in"),
        ("+40700000009", 403, "not_registered"),
        ("+40700000003", 403, "not_allowed"),  # a medic
    ],
)
async def test_the_staff_list_is_for_das(client, add_user, das, token, status, reason):
    await add_user("+40700000003", Role.medic)
    headers = signed_in(token) if token else {}
    r = await client.get("/api/staff", headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})


async def patch_staff(client, user_id, body, token=DAS):
    return await client.patch(
        f"/api/staff/{user_id}", json=body, headers=signed_in(token)
    )


async def test_das_edits_a_medic(client, db, das):
    medic = (await post(client, MEDIC)).json()
    user = await db.scalar(select(User).where(User.phone_e164 == medic["phone_e164"]))
    r = await patch_staff(
        client,
        user.id,
        {
            "display_name": "Dr. Ion Popescu",
            "practice": "CMI Nou",
            "phone": "0700 000 099",
        },
    )
    assert r.status_code == 200
    assert r.json() == {
        "id": str(user.id),
        "display_name": "Dr. Ion Popescu",
        "phone_e164": medic["phone_e164"],
        "practice": "CMI Nou",
        "roles": ["medic"],
        "on_duty": False,
    }  # the phone stays (Q8)


async def test_an_empty_patch_changes_nothing(client, das):  # Review Focus 3
    r = await patch_staff(client, das.id, {})
    assert (r.status_code, r.json()["display_name"]) == (200, "DAS Test")


async def test_practice_needs_a_medic(client, das):
    r = await patch_staff(client, das.id, {"practice": "CMI"})
    assert (r.status_code, r.json()) == (422, {"detail": {"reason": "not_medic"}})


async def test_only_staff_can_be_edited(client, add_user, das):
    nobody = await add_user("+40700000004")  # a user row without a das or medic grant
    for user_id in (nobody.id, uuid.uuid4()):
        r = await patch_staff(client, user_id, {"display_name": "X"})
        assert (r.status_code, r.json()) == (404, {"detail": {"reason": "not_found"}})


async def test_a_medic_cannot_edit_staff(client, add_user, das):
    await add_user("+40700000003", Role.medic)
    r = await patch_staff(client, das.id, {"display_name": "X"}, token="+40700000003")
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})


async def listed(client):
    r = await client.get("/api/staff", headers=signed_in(DAS))
    return {s["phone_e164"]: s for s in r.json()}


async def test_removing_a_medic_role(client, das, add_user):
    medic = await add_user("+40700000002", Role.medic)
    path = f"/api/staff/{medic.id}/roles/medic"
    assert (await client.delete(path, headers=signed_in(DAS))).status_code == 204
    assert (
        await client.delete(path, headers=signed_in(DAS))
    ).status_code == 204  # a repeat
    assert "+40700000002" not in await listed(client)


async def test_removing_das_takes_them_off_duty(client, db, das, add_user):
    other = await add_user("+40700000003", Role.das)
    other.on_duty = True
    await db.commit()
    r = await client.delete(f"/api/staff/{other.id}/roles/das", headers=signed_in(DAS))
    assert r.status_code == 204
    await db.refresh(other)
    assert other.on_duty is False


async def test_the_last_das_stays(client, db, das):
    r = await client.delete(f"/api/staff/{das.id}/roles/das", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    assert await db.scalar(select(Grant).where(Grant.user_id == das.id)) is not None


async def test_removing_your_own_das_role(client, das, add_user):  # Review Focus 2
    await add_user("+40700000003", Role.das)
    r = await client.delete(f"/api/staff/{das.id}/roles/das", headers=signed_in(DAS))
    assert r.status_code == 204
    r = await client.get("/api/profile", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_registered"}})


async def test_only_staff_roles_are_removed_here(client, das):
    r = await client.delete(
        f"/api/staff/{das.id}/roles/caregiver", headers=signed_in(DAS)
    )
    assert r.status_code == 422


async def test_on_duty_switches(client, das, add_user):
    other = await add_user("+40700000003", Role.das)
    for user, phone in ((das, DAS), (other, "+40700000003")):
        r = await client.put(
            "/api/staff/on-duty", json={"user_id": str(user.id)}, headers=signed_in(DAS)
        )
        assert r.status_code == 204
        assert [p for p, s in (await listed(client)).items() if s["on_duty"]] == [phone]
    r = await client.delete("/api/staff/on-duty", headers=signed_in(DAS))
    assert r.status_code == 204
    assert not any(s["on_duty"] for s in (await listed(client)).values())


async def test_on_duty_needs_a_das(client, das, add_user):
    medic = await add_user("+40700000002", Role.medic)
    r = await client.put(
        "/api/staff/on-duty", json={"user_id": str(medic.id)}, headers=signed_in(DAS)
    )
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})


async def test_two_on_duty_switches_at_once(client, das, add_user):  # Review Focus 1
    other = await add_user("+40700000003", Role.das)
    rs = await asyncio.gather(
        *(
            client.put(
                "/api/staff/on-duty",
                json={"user_id": str(u.id)},
                headers=signed_in(DAS),
            )
            for u in (das, other)
        )
    )
    assert [r.status_code for r in rs] == [204, 204]
    assert sum(s["on_duty"] for s in (await listed(client)).values()) == 1


@pytest.mark.parametrize(
    ("verb", "path", "body"),
    [
        ("PATCH", f"/api/staff/{uuid.uuid4()}", {}),
        ("DELETE", f"/api/staff/{uuid.uuid4()}/roles/medic", None),
        ("PUT", "/api/staff/on-duty", {"user_id": str(uuid.uuid4())}),
        ("DELETE", "/api/staff/on-duty", None),
    ],
)
@pytest.mark.parametrize(
    ("token", "status", "reason"),
    [
        (None, 401, "not_signed_in"),
        ("+40700000009", 403, "not_registered"),
        ("+40700000002", 403, "not_allowed"),  # a medic
    ],
)
async def test_staff_changes_are_for_das(
    client, add_user, das, verb, path, body, token, status, reason
):
    await add_user("+40700000002", Role.medic)
    headers = signed_in(token) if token else {}
    r = await client.request(verb, path, json=body, headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"
