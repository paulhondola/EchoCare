"""Enrollment states: submit and accept (#18, UC-01 step 6, UC-04 step 1)."""

import asyncio

import pytest
from sqlalchemy import update

from app import main
from app.models import EnrollmentState, Role, Senior

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
SENIOR = "+40700000005"

MARIA = {
    "full_name": "Maria Pop",
    "form_of_address": "doamna Maria",
    "phone": "0700 000 005",
    "street": "Str. Florilor",
    "street_number": "12",
}
ANA = {"display_name": "Ana Pop", "relation": "fiica", "phone": "0700 000 004"}

NOT_FOUND = (404, {"detail": {"reason": "not_found"}})
NOT_ALLOWED = (403, {"detail": {"reason": "not_allowed"}})
ALREADY_DONE = (409, {"detail": {"reason": "already_done"}})
WRONG_STATE = (409, {"detail": {"reason": "wrong_state"}})


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(r) -> tuple[int, dict]:
    return r.status_code, r.json()


@pytest.fixture
async def staff(add_user):
    await add_user(DAS, Role.das, name="DAS Test")
    await add_user(OTHER_MEDIC, Role.medic, name="Dr. Alt")
    return await add_user(MEDIC, Role.medic, name="Dr. Pop")


async def register(client, body=MARIA, caregiver=True) -> str:
    """A draft, ready to submit unless told otherwise; its id."""
    r = await client.post("/api/seniors", json=body, headers=signed_in(MEDIC))
    assert r.status_code == 201, r.text
    senior_id = r.json()["id"]
    if caregiver:
        r = await client.post(
            f"/api/seniors/{senior_id}/caregivers", json=ANA, headers=signed_in(MEDIC)
        )
        assert r.status_code == 201, r.text
    return senior_id


async def submit(client, senior_id, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/submit", headers=signed_in(token)
    )


async def accept(client, senior_id, token=DAS):
    return await client.post(
        f"/api/seniors/{senior_id}/accept", headers=signed_in(token)
    )


async def enrollments(client, token=DAS):
    return await client.get("/api/enrollments", headers=signed_in(token))


async def test_from_draft_to_accepted(client, staff):
    """#18's done-when, end to end."""
    maria = await register(client)
    assert (await enrollments(client)).json() == []
    r = await client.get(f"/api/seniors/{maria}", headers=signed_in(DAS))
    assert refusal(r) == NOT_FOUND
    assert refusal(await accept(client, maria)) == NOT_FOUND

    r = await submit(client, maria)
    assert r.status_code == 200
    assert r.json() == {
        "id": maria,
        "full_name": "Maria Pop",
        "form_of_address": "doamna Maria",
        "enrollment_state": "submitted",
    }
    assert [s["id"] for s in (await enrollments(client)).json()] == [maria]
    r = await client.get(f"/api/seniors/{maria}", headers=signed_in(DAS))
    assert r.status_code == 200

    r = await accept(client, maria)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "accepted")
    assert (await enrollments(client)).json() == []
    assert refusal(await accept(client, maria)) == ALREADY_DONE
    # Still DAS's to see, and the medic's
    for token in (DAS, MEDIC):
        r = await client.get(f"/api/seniors/{maria}", headers=signed_in(token))
        assert r.json()["enrollment_state"] == "accepted"


async def test_a_second_submit_is_already_done(client, staff):
    maria = await register(client)
    await submit(client, maria)
    assert refusal(await submit(client, maria)) == ALREADY_DONE


async def test_submit_after_accept_is_wrong_state(client, staff):
    maria = await register(client)
    await submit(client, maria)
    await accept(client, maria)
    assert refusal(await submit(client, maria)) == WRONG_STATE


@pytest.mark.parametrize(
    "state",
    [EnrollmentState.active, EnrollmentState.refused, EnrollmentState.unreachable],
)
async def test_accept_only_from_submitted(client, db, staff, state):
    maria = await register(client)
    await db.execute(
        update(Senior).where(Senior.id == maria).values(enrollment_state=state)
    )
    await db.commit()
    assert refusal(await accept(client, maria)) == WRONG_STATE


async def test_two_accepts_at_once(client, staff):
    maria = await register(client)
    await submit(client, maria)
    first, second = await asyncio.gather(accept(client, maria), accept(client, maria))
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert ALREADY_DONE in (refusal(first), refusal(second))


async def test_removing_the_caregiver_during_a_submit(client, staff, monkeypatch):
    # Submit pauses between its check and its move, and the removal comes in that
    # gap. The senior's row lock makes it wait, so DAS never gets a request without
    # a caregiver (04 §2).
    checked = main.missing_to_submit

    async def slow_check(session, senior):
        missing = await checked(session, senior)
        await asyncio.sleep(0.3)
        return missing

    monkeypatch.setattr(main, "missing_to_submit", slow_check)
    maria = await register(client)
    detail = await client.get(f"/api/seniors/{maria}", headers=signed_in(MEDIC))
    ana = detail.json()["caregivers"][0]["user_id"]

    async def remove_in_the_gap():
        await asyncio.sleep(0.1)
        return await client.delete(
            f"/api/seniors/{maria}/caregivers/{ana}", headers=signed_in(MEDIC)
        )

    submitted, removed = await asyncio.gather(
        submit(client, maria), remove_in_the_gap()
    )
    assert submitted.status_code == 200
    assert refusal(removed) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["caregiver"]}},
    )


@pytest.mark.parametrize(
    ("change", "caregiver", "missing"),
    [
        ({"street": None}, True, ["street"]),
        ({"street": "", "street_number": "  "}, True, ["street", "street_number"]),
        ({}, False, ["caregiver"]),
    ],
)
async def test_an_incomplete_draft_stays_a_draft(
    client, staff, change, caregiver, missing
):
    maria = await register(client, {**MARIA, **change}, caregiver=caregiver)
    r = await submit(client, maria)
    assert refusal(r) == (
        422,
        {"detail": {"reason": "incomplete", "missing": missing}},
    )
    r = await client.get(f"/api/seniors/{maria}", headers=signed_in(MEDIC))
    assert r.json()["enrollment_state"] == "draft"


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (OTHER_MEDIC, NOT_FOUND),  # does not reach another medic's draft
        (DAS, NOT_ALLOWED),
        (CAREGIVER, NOT_ALLOWED),
        (SENIOR, NOT_ALLOWED),
    ],
)
async def test_only_her_medic_submits(client, staff, token, expected):
    maria = await register(client)
    assert refusal(await submit(client, maria, token)) == expected


@pytest.mark.parametrize("token", [MEDIC, CAREGIVER, SENIOR])
async def test_only_das_accepts(client, staff, token):
    maria = await register(client)
    await submit(client, maria)
    assert refusal(await accept(client, maria, token)) == NOT_ALLOWED


@pytest.mark.parametrize("token", [MEDIC, CAREGIVER])
async def test_only_das_lists_enrollments(client, staff, token):
    await register(client)
    assert refusal(await enrollments(client, token)) == NOT_ALLOWED


async def test_enrollments_oldest_first(client, staff):
    first = await register(client)
    second = await register(client, {**MARIA, "full_name": "Ana Ionescu"})
    for senior_id in (second, first):
        await submit(client, senior_id)
    assert [s["id"] for s in (await enrollments(client)).json()] == [first, second]
