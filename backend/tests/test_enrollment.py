"""Enrollment states: submit, accept and GET /enrollments (seniors §3.4; UC-01 step 6,
UC-04 step 1)."""

import asyncio
import uuid

import pytest

from app.models import EnrollmentState, Role

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
LANDLINE = "+40256123456"
ADDRESS = {"street": "Str. Daliei", "street_number": "12"}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str, **extra) -> dict:
    return {"detail": {"reason": reason, **extra}}


@pytest.fixture
async def medic(add_user):
    return await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


@pytest.fixture
async def draft(add_senior, medic):
    return await add_senior(LANDLINE, medic=medic, **ADDRESS)


async def submit(client, senior_id, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/submit", headers=signed_in(token)
    )


async def accept(client, senior_id, token=DAS):
    return await client.post(
        f"/api/seniors/{senior_id}/accept", headers=signed_in(token)
    )


async def enrollments(client):
    r = await client.get("/api/enrollments", headers=signed_in(DAS))
    assert r.status_code == 200
    return [s["full_name"] for s in r.json()]


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/seniors/{id}/submit"),
        ("POST", "/api/seniors/{id}/accept"),
        ("GET", "/api/enrollments"),
    ],
)
async def test_refusals(client, draft, method, path, headers, status, reason):
    r = await client.request(method, path.format(id=draft.id), headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_submit(client, draft):
    r = await submit(client, draft.id)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "submitted")
    assert r.json()["id"] == str(draft.id)


@pytest.mark.parametrize(
    ("address", "missing"),
    [
        ({"street_number": "12"}, ["street"]),
        ({"street": "Str. Daliei"}, ["street_number"]),
        ({}, ["street", "street_number"]),
    ],
)
async def test_submit_needs_the_address(
    client, db, add_senior, medic, address, missing
):
    senior = await add_senior(LANDLINE, medic=medic, **address)
    r = await submit(client, senior.id)
    assert (r.status_code, r.json()) == (422, refusal("missing_fields", fields=missing))
    await db.refresh(senior)
    assert senior.enrollment_state == EnrollmentState.draft


async def test_a_second_submit_is_refused(client, draft):
    await submit(client, draft.id)
    r = await submit(client, draft.id)
    assert (r.status_code, r.json()) == (409, refusal("wrong_state"))


async def test_two_submits_at_once(client, draft):
    first, second = await asyncio.gather(
        submit(client, draft.id), submit(client, draft.id)
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_das_sees_her_once_submitted(client, draft, das):
    page = f"/api/seniors/{draft.id}"
    assert (await client.get(page, headers=signed_in(DAS))).status_code == 404
    assert await enrollments(client) == []
    await submit(client, draft.id)
    assert (await client.get(page, headers=signed_in(DAS))).status_code == 200
    assert await enrollments(client) == ["Maria Pop"]


async def test_enrollments_are_oldest_first(client, add_senior, medic, das):
    submitted = EnrollmentState.submitted
    await add_senior("+40256000001", "First", medic, enrollment_state=submitted)
    await add_senior("+40256000002", "Second", medic, enrollment_state=submitted)
    await add_senior("+40256000003", "Still a draft", medic)
    assert await enrollments(client) == ["First", "Second"]


async def test_accept(client, draft, das):
    await submit(client, draft.id)
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "accepted")
    assert await enrollments(client) == []
    # A second accept is refused (seniors SE13).
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()) == (409, refusal("wrong_state"))


async def test_two_accepts_at_once(client, draft, das):
    await submit(client, draft.id)
    first, second = await asyncio.gather(
        accept(client, draft.id), accept(client, draft.id)
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_a_draft_is_outside_das_reach(client, draft, das):
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    r = await accept(client, uuid.uuid4())
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_only_das_accepts_and_only_a_medic_submits(client, draft, das):
    r = await submit(client, draft.id, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    await submit(client, draft.id)
    r = await accept(client, draft.id, token=MEDIC)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    r = await client.get("/api/enrollments", headers=signed_in(MEDIC))
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_another_medic_cannot_submit_her(client, add_user, draft):
    await add_user(OTHER_MEDIC, Role.medic)
    r = await submit(client, draft.id, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/seniors"),
        ("GET", "/api/seniors/{id}"),
        ("POST", "/api/seniors"),
        ("PUT", "/api/seniors/{id}"),
        ("POST", "/api/seniors/{id}/caregivers"),
        ("DELETE", "/api/seniors/{id}/caregivers/{id}"),
        ("POST", "/api/seniors/{id}/submit"),
        ("POST", "/api/seniors/{id}/accept"),
        ("GET", "/api/enrollments"),
    ],
)
async def test_a_user_with_no_grant_left_is_not_registered(
    client, add_user, draft, method, path
):
    # Every senior endpoint, now that they all exist (seniors §6.4, the second row).
    await add_user(CAREGIVER)  # a user row whose grants were all removed
    r = await client.request(
        method, path.format(id=draft.id), headers=signed_in(CAREGIVER)
    )
    assert (r.status_code, r.json()) == (403, refusal("not_registered"))


async def test_the_story(client, add_user, medic, das):
    """seniors §1, steps 2 to 6, through the API alone."""
    await add_user(OTHER_MEDIC, Role.medic)
    as_medic, as_das = signed_in(MEDIC), signed_in(DAS)
    as_caregiver = signed_in(CAREGIVER)

    # 2. The medic registers doamna Maria with a caregiver, and submits.
    made = await client.post(
        "/api/seniors",
        json={
            "full_name": "Maria Popescu",
            "form_of_address": "doamna Maria",
            "phone": "0256 123 456",
            **ADDRESS,
        },
        headers=as_medic,
    )
    page = f"/api/seniors/{made.json()['id']}"
    added = await client.post(
        f"{page}/caregivers",
        json={
            "display_name": "Ioana Pop",
            "relation": "fiică",
            "phone": "0700 000 004",
        },
        headers=as_medic,
    )
    assert (made.status_code, added.status_code) == (201, 201)

    # 5a. DAS cannot see a draft.
    assert (await client.get(page, headers=as_das)).status_code == 404
    assert (await client.post(f"{page}/submit", headers=as_medic)).status_code == 200

    # 3. The caregiver's /me names her, and their list holds only her.
    grant = (await client.get("/api/me", headers=as_caregiver)).json()["grants"][0]
    assert grant["senior_form_of_address"] == "doamna Maria"
    seniors = (await client.get("/api/seniors", headers=as_caregiver)).json()
    assert [s["id"] for s in seniors] == [made.json()["id"]]

    # 4. Another medic gets 404 for her.
    assert (await client.get(page, headers=signed_in(OTHER_MEDIC))).status_code == 404

    # 5b. DAS sees her now, accepts her, and a second accept is refused.
    assert (await client.get(page, headers=as_das)).status_code == 200
    assert (await client.post(f"{page}/accept", headers=as_das)).status_code == 200
    assert (await client.post(f"{page}/accept", headers=as_das)).status_code == 409

    # 6. The medic removes the caregiver; their next request is not_registered.
    removed = await client.delete(
        f"{page}/caregivers/{added.json()['user_id']}", headers=as_medic
    )
    assert removed.status_code == 204
    r = await client.get("/api/seniors", headers=as_caregiver)
    assert (r.status_code, r.json()) == (403, refusal("not_registered"))
