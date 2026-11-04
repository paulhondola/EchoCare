"""Who reaches which senior (auth-layer §3.6, seniors §3.1), read through
GET /seniors and GET /seniors/{id}, and what `?role=` narrows (seniors SE6)."""

import logging
import uuid

import pytest
from sqlalchemy import delete, func, select, text

from app.models import EnrollmentState, Grant, Role, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
SENIOR_DRAFT = "+40700000005"
SENIOR_SUBMITTED = "+40700000006"
OTHER_CAREGIVER = "+40700000007"
EX_MEDIC = "+40700000008"
NOT_FOUND = {"detail": {"reason": "not_found"}}
NOT_ALLOWED = {"detail": {"reason": "not_allowed"}}
WRONG_STATE = {"detail": {"reason": "wrong_state"}}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seniors(db, add_user, add_senior):
    """Four seniors, named for what they are, and everyone who may look.
    Returns their ids by name."""
    medic = await add_user(MEDIC, Role.medic)
    other_medic = await add_user(OTHER_MEDIC, Role.medic)
    ex_medic = await add_user(EX_MEDIC, Role.medic)
    await add_user(DAS, Role.das)
    submitted = EnrollmentState.submitted
    draft = await add_senior("+40256000001", "draft", medic)
    sent = await add_senior(
        "+40256000002", "submitted", medic, enrollment_state=submitted
    )
    other = await add_senior(
        "+40256000003", "other", other_medic, enrollment_state=submitted
    )
    orphan = await add_senior("+40256000004", "orphan", ex_medic)
    caregiver = await add_user(CAREGIVER)
    other_caregiver = await add_user(OTHER_CAREGIVER)
    senior_draft = await add_user(SENIOR_DRAFT)
    senior_submitted = await add_user(SENIOR_SUBMITTED)
    db.add_all(
        [
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=draft.id),
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=sent.id),
            Grant(user_id=other_caregiver.id, role=Role.caregiver, senior_id=other.id),
            Grant(user_id=senior_draft.id, role=Role.senior, senior_id=draft.id),
            Grant(user_id=senior_submitted.id, role=Role.senior, senior_id=sent.id),
            # Once a medic, now only a caregiver; the orphan's medic_id is still theirs.
            Grant(user_id=ex_medic.id, role=Role.caregiver, senior_id=other.id),
        ]
    )
    await db.execute(
        delete(Grant).where(Grant.user_id == ex_medic.id, Grant.role == Role.medic)
    )
    await db.commit()
    return {s.full_name: s.id for s in (draft, sent, other, orphan)}


REACH = [
    (MEDIC, {"draft", "submitted"}),
    (OTHER_MEDIC, {"other"}),
    (EX_MEDIC, {"other"}),  # as a caregiver; not the orphan they registered
    (CAREGIVER, {"draft", "submitted"}),
    (SENIOR_DRAFT, {"draft"}),
    (SENIOR_SUBMITTED, {"submitted"}),
    (OTHER_CAREGIVER, {"other"}),
    (DAS, {"submitted", "other"}),  # never a draft
]


@pytest.mark.parametrize(("token", "reached"), REACH)
async def test_the_list_is_what_the_caller_reaches(client, seniors, token, reached):
    r = await client.get("/api/seniors", headers=signed_in(token))
    assert r.status_code == 200
    assert {s["full_name"] for s in r.json()} == reached


@pytest.mark.parametrize(("token", "reached"), REACH)
async def test_a_senior_outside_reach_is_not_found(client, seniors, token, reached):
    for name, senior_id in seniors.items():
        r = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(token))
        if name in reached:
            assert (r.status_code, r.json()["full_name"]) == (200, name)
        else:
            assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_an_id_that_does_not_exist_is_not_found(client, seniors):
    r = await client.get(f"/api/seniors/{uuid.uuid4()}", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_by_name(client, seniors):
    r = await client.get("/api/seniors", headers=signed_in(MEDIC))
    assert [s["full_name"] for s in r.json()] == ["draft", "submitted"]


async def test_one_row(client, seniors):
    r = await client.get("/api/seniors", headers=signed_in(SENIOR_DRAFT))
    [row] = r.json()
    assert row.pop("created_at")  # 04 §1; a draft has neither of the other two
    assert [row] == [
        {
            "id": str(seniors["draft"]),
            "full_name": "draft",
            "form_of_address": "doamna Maria",
            "phone_e164": "+40256000001",
            "phone_is_landline": False,
            "enrollment_state": "draft",
            "code": None,  # no code until active (Q17)
            "reason": None,
            "since": None,
            "submitted_at": None,
            "accepted_at": None,
        }
    ]


@pytest.mark.parametrize(
    ("role", "reached"),
    [
        (None, {"draft", "submitted", "other"}),  # the union (AL2)
        ("medic", {"draft", "submitted"}),
        ("caregiver", {"other"}),
        ("senior", set()),
        ("das", set()),  # a role they do not hold: an empty list, not a refusal
    ],
)
async def test_role_narrows_the_list(client, db, seniors, role, reached):
    # The medic is also the caregiver of another medic's senior.
    medic_id = await db.scalar(select(User.id).where(User.phone_e164 == MEDIC))
    db.add(Grant(user_id=medic_id, role=Role.caregiver, senior_id=seniors["other"]))
    await db.commit()
    r = await client.get(
        "/api/seniors", params={"role": role} if role else {}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 200
    assert {s["full_name"] for s in r.json()} == reached


async def test_each_role_reaches_through_its_own_grants(
    client, db, add_user, add_senior
):
    # One user, the caregiver of one senior and the number of another: a role's reach
    # holds only the grants of that role.
    user = await add_user(CAREGIVER)
    cared = await add_senior("+40256000001", "cared")
    own = await add_senior("+40256000002", "own")
    db.add_all(
        [
            Grant(user_id=user.id, role=Role.caregiver, senior_id=cared.id),
            Grant(user_id=user.id, role=Role.senior, senior_id=own.id),
        ]
    )
    await db.commit()
    for params, reached in [
        ({"role": "caregiver"}, {"cared"}),
        ({"role": "senior"}, {"own"}),
        ({}, {"cared", "own"}),
    ]:
        r = await client.get(
            "/api/seniors", params=params, headers=signed_in(CAREGIVER)
        )
        assert {s["full_name"] for s in r.json()} == reached


async def test_an_unknown_role_is_a_422(client, seniors):
    r = await client.get("/api/seniors?role=nurse", headers=signed_in(MEDIC))
    assert r.status_code == 422


async def test_a_state_this_copy_does_not_know_is_served(client, db, seniors):
    # Written by a newer copy during a deploy (ADR-001 §2.3). It is not draft, so DAS
    # reaches it, and it is served as the plain string it is.
    await db.execute(
        text("UPDATE seniors SET enrollment_state = 'paused' WHERE id = :id"),
        {"id": seniors["draft"]},
    )
    await db.commit()
    for token in (DAS, MEDIC):
        r = await client.get(
            f"/api/seniors/{seniors['draft']}", headers=signed_in(token)
        )
        assert (r.status_code, r.json()["enrollment_state"]) == (200, "paused")
    listed = await client.get("/api/seniors", headers=signed_in(DAS))
    assert "paused" in [s["enrollment_state"] for s in listed.json()]


async def test_a_refusal_is_logged_without_a_number(client, seniors, caplog):
    caplog.set_level(logging.INFO, logger="echocare")
    await client.get(f"/api/seniors/{seniors['draft']}", headers=signed_in(DAS))
    assert "refused not_found: user " in caplog.text
    assert f"senior {seniors['draft']}" in caplog.text
    assert DAS not in caplog.text  # the user id, never the number (auth-layer AL15)


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
@pytest.mark.parametrize("path", ["/api/seniors", "/api/seniors/{id}"])
async def test_refusals(client, seniors, path, headers, status, reason):
    r = await client.get(path.format(id=seniors["submitted"]), headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})


CHANGE = {
    "full_name": "Changed",
    "form_of_address": "doamna Maria",
    "phone": "0256 123 456",
    "street": "Str. Daliei",
    "street_number": "12",
}
NEW_CAREGIVER = {"display_name": "Ioana", "relation": "fiică", "phone": "0700 000 009"}


@pytest.mark.parametrize(
    ("token", "closing", "refused"),
    [
        (OTHER_MEDIC, "submit", (403, NOT_ALLOWED)),
        # Accept finds the draft through the caregiver grant; a draft is not accepted.
        (DAS, "accept", (409, WRONG_STATE)),
    ],
)
async def test_reading_as_a_caregiver_gives_no_command(
    client, db, add_user, add_senior, token, closing, refused
):
    # The caregiver grant of another medic or of DAS lets them read the draft and
    # nothing more: the medic's commands are for the medic who registered her (04 §2).
    medic = await add_user(MEDIC, Role.medic)
    other_medic = await add_user(OTHER_MEDIC, Role.medic)
    das = await add_user(DAS, Role.das)
    senior = await add_senior(
        "+40256123456", medic=medic, street="Str. Daliei", street_number="12"
    )
    db.add_all(
        Grant(user_id=u.id, role=Role.caregiver, senior_id=senior.id)
        for u in (other_medic, das)
    )
    await db.commit()
    page = f"/api/seniors/{senior.id}"
    headers = signed_in(token)
    assert (await client.get(page, headers=headers)).status_code == 200
    commands = [
        ("PUT", page, CHANGE, (403, NOT_ALLOWED)),
        ("POST", f"{page}/caregivers", NEW_CAREGIVER, (403, NOT_ALLOWED)),
        ("DELETE", f"{page}/caregivers/{other_medic.id}", None, (403, NOT_ALLOWED)),
        ("POST", f"{page}/{closing}", None, refused),
    ]
    caregivers = (
        select(func.count()).select_from(Grant).where(Grant.role == Role.caregiver)
    )
    for method, path, body, expected in commands:
        r = await client.request(method, path, json=body, headers=headers)
        assert (r.status_code, r.json()) == expected
        await db.refresh(senior)
        assert (senior.full_name, senior.enrollment_state) == ("Maria Pop", "draft")
        assert await db.scalar(caregivers) == 2
