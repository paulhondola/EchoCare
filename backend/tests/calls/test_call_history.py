"""GET /seniors/{id}/calls and GET /calls/{id}/transcript (04 §1, crud-completion §4.3)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY

import pytest
from sqlalchemy import update

from app.models import (
    Answer,
    Call,
    CallTurn,
    EnrollmentState,
    Grant,
    Role,
    Senior,
    StatusReport,
)

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
SENIOR = "+40700000101"  # Maria's own number
STRANGER = "+40700000009"

NOT_FOUND = {"detail": {"reason": "not_found"}}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def people(db, add_user, add_senior):
    """Maria, past draft: her medic, a caregiver and herself; DAS and another medic."""
    await add_user(DAS, Role.das)
    await add_user(OTHER_MEDIC, Role.medic)
    medic = await add_user(MEDIC, Role.medic)
    maria = await add_senior(
        SENIOR, medic=medic, enrollment_state=EnrollmentState.accepted
    )
    caregiver = await add_user(CAREGIVER)
    herself = await add_user(SENIOR)
    db.add_all(
        [
            Grant(
                user_id=caregiver.id,
                role=Role.caregiver,
                senior_id=maria.id,
                relation="fiică",
            ),
            Grant(user_id=herself.id, role=Role.senior, senior_id=maria.id),
        ]
    )
    await db.commit()
    return SimpleNamespace(maria=maria)


def call(senior: Senior, **columns) -> Call:
    return Call(
        **{
            "senior_id": senior.id,
            "trigger": "watch",
            "starting_severity": "yellow",
            "state": "completed",
            "due_at": datetime.now(UTC),
            **columns,
        }
    )


async def test_everyone_who_reaches_her_sees_her_calls(client, db, people):
    now = datetime.now(UTC)
    older = call(people.maria, created_at=now - timedelta(days=1))
    newer = call(
        people.maria,
        created_at=now - timedelta(hours=1),
        state="handed_over",
        final_severity="red",
        final_certainty="high",
        reason="căzătură",
        summary="A căzut.",
    )
    test = call(people.maria, trigger="test", created_at=now)
    db.add_all([older, newer, test])
    await db.commit()

    for token in (DAS, MEDIC, CAREGIVER, SENIOR):
        r = await client.get(
            f"/api/seniors/{people.maria.id}/calls", headers=signed_in(token)
        )
        assert r.status_code == 200
        assert [c["id"] for c in r.json()] == [str(newer.id), str(older.id)]
    assert r.json()[0] == {
        "id": str(newer.id),
        "trigger": "watch",
        "state": "handed_over",
        "due_at": ANY,
        "started_at": None,
        "ended_at": None,
        "final_severity": "red",
        "final_certainty": "high",
        "reason": "căzătură",
        "summary": "A căzut.",
    }


async def test_a_queued_call_is_listed(client, db, people):
    db.add(call(people.maria, state="queued"))
    await db.commit()
    r = await client.get(
        f"/api/seniors/{people.maria.id}/calls", headers=signed_in(MEDIC)
    )
    assert [(c["state"], c["started_at"]) for c in r.json()] == [("queued", None)]


async def test_someone_else_does_not_see_her_calls(client, people):
    r = await client.get(
        f"/api/seniors/{people.maria.id}/calls", headers=signed_in(OTHER_MEDIC)
    )
    assert (r.status_code, r.json()) == (404, NOT_FOUND)


@pytest.fixture
async def recorded(db, people):
    """One call, its turns saved out of order, a report and two answers."""
    now = datetime.now(UTC)
    c = call(people.maria, state="handed_over", final_severity="red")
    db.add(c)
    await db.flush()
    db.add_all(
        [
            CallTurn(
                call_id=c.id,
                position=2,
                speaker="senior",
                kind="speech",
                content="bine",
            ),
            CallTurn(
                call_id=c.id,
                position=1,
                speaker="agent",
                kind="speech",
                content="Cum vă simțiți?",
            ),
            StatusReport(
                call_id=c.id, source="rules", severity="red", reason="căzătură"
            ),
            Answer(
                call_id=c.id,
                field="feeling",
                value="ok",
                clear=True,
                quote="bine",
                at=now,
            ),
            Answer(
                call_id=c.id,
                field="shelter",
                value="yes",
                clear=False,
                quote="da",
                at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db.commit()
    return c


async def transcript(client, call_id, token):
    return await client.get(
        f"/api/calls/{call_id}/transcript", headers=signed_in(token)
    )


async def test_the_transcript(client, recorded):
    r = await transcript(client, recorded.id, MEDIC)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(recorded.id)
    assert body["final_severity"] == "red"  # by name, not "2"
    assert [t["content"] for t in body["turns"]] == ["Cum vă simțiți?", "bine"]
    assert [(r["source"], r["severity"]) for r in body["reports"]] == [("rules", "red")]
    # Answers by time, not by when they were saved.
    assert body["answers"] == [
        {"field": "shelter", "value": "yes", "clear": False, "quote": "da", "at": ANY},
        {"field": "feeling", "value": "ok", "clear": True, "quote": "bine", "at": ANY},
    ]
    assert (await transcript(client, recorded.id, DAS)).status_code == 200


async def test_a_test_calls_transcript_is_served(client, db, people):
    c = call(people.maria, trigger="test")
    db.add(c)
    await db.commit()
    assert (await transcript(client, c.id, MEDIC)).status_code == 200


@pytest.mark.parametrize("token", [CAREGIVER, SENIOR, OTHER_MEDIC])
async def test_the_transcript_is_for_her_medic_and_das(client, recorded, token):
    r = await transcript(client, recorded.id, token)
    assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_a_call_that_does_not_exist_is_not_found(client, people):
    r = await transcript(client, uuid.uuid4(), MEDIC)
    assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_das_does_not_see_a_drafts_transcript(client, db, people, recorded):
    await db.execute(
        update(Senior)
        .where(Senior.id == people.maria.id)
        .values(enrollment_state=EnrollmentState.draft)
    )
    await db.commit()
    r = await transcript(client, recorded.id, DAS)
    assert (r.status_code, r.json()) == (404, NOT_FOUND)
    assert (await transcript(client, recorded.id, MEDIC)).status_code == 200


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in(STRANGER), 403, "not_registered"),
    ],
)
async def test_signed_out_and_unknown(client, people, headers, status, reason):
    for path in (
        f"/api/seniors/{people.maria.id}/calls",
        f"/api/calls/{uuid.uuid4()}/transcript",
    ):
        r = await client.get(path, headers=headers)
        assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
        assert r.headers.get("www-authenticate") == (
            "Bearer" if status == 401 else None
        )


@pytest.mark.parametrize(
    ("state", "badge"),
    [
        ("queued", False),
        ("ringing", True),
        ("in_progress", True),
        ("completed", False),
    ],
)
async def test_the_page_says_whether_a_call_is_live(client, db, people, state, badge):
    """The "call in progress" badge (UC-12): ringing or live, for every role."""
    db.add(call(people.maria, state=state))
    await db.commit()
    for who in (CAREGIVER, MEDIC, DAS):
        r = await client.get(f"/api/seniors/{people.maria.id}", headers=signed_in(who))
        assert r.json()["call_in_progress"] is badge


async def test_a_scripted_test_call_lights_no_badge(client, db, people):
    """05 §1: the history leaves it out, so the badge would point at nothing."""
    db.add(call(people.maria, state="ringing", trigger="test"))
    await db.commit()
    r = await client.get(
        f"/api/seniors/{people.maria.id}", headers=signed_in(CAREGIVER)
    )
    assert r.json()["call_in_progress"] is False
