"""The senior_summaries versions: one per call, newest wins (#63, design §4)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.models import Call, EnrollmentState, Grant, Role, Senior, SummaryVersion
from app.seniors.schemas import Citation, FollowUp, SummaryContent, Trend
from app.seniors.service import add_summary, latest_summary, read_content

SENIOR = "+40700000111"


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


async def add_call(db, senior) -> uuid.UUID:
    call = Call(
        senior_id=senior.id,
        trigger="watch",
        starting_severity="yellow",
        state="completed",
        due_at=datetime.now(UTC),
    )
    db.add(call)
    await db.flush()
    return call.id


def content(narrative: str = "Se simte bine.") -> SummaryContent:
    return SummaryContent(follow_ups=[], how_to_talk=[], trends=[], narrative=narrative)


async def test_a_version_is_kept_per_call(db, senior):
    call_id = await add_call(db, senior)
    for _ in range(2):
        add_summary(
            db,
            senior_id=senior.id,
            call_id=call_id,
            previous_id=None,
            content=content(),
            model="m",
        )
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_latest_is_the_newest(db, senior):
    first_call = await add_call(db, senior)
    second_call = await add_call(db, senior)
    add_summary(
        db,
        senior_id=senior.id,
        call_id=first_call,
        previous_id=None,
        content=content("unu"),
        model="m",
    )
    await db.commit()  # now() is the transaction's time: a version per transaction
    first = await latest_summary(db, senior.id)
    add_summary(
        db,
        senior_id=senior.id,
        call_id=second_call,
        previous_id=first.id,
        content=content("doi"),
        model="m",
    )
    await db.commit()
    latest = await latest_summary(db, senior.id)
    assert latest.call_id == second_call
    assert latest.previous_id == first.id
    assert read_content(latest).narrative == "doi"


def test_bounds_hold():
    follow_up = FollowUp(topic="t", question="q", call_id=uuid.uuid4(), quote="citat")
    with pytest.raises(ValidationError):
        SummaryContent(
            follow_ups=[follow_up] * 4, how_to_talk=[], trends=[], narrative="x"
        )
    one = Citation(call_id=uuid.uuid4(), quote="citat")
    with pytest.raises(ValidationError):
        SummaryContent(
            follow_ups=[],
            how_to_talk=[],
            trends=[Trend(note="n", direction="worse", evidence=[one])],
            narrative="x",
        )
    with pytest.raises(ValidationError):
        content("x" * 601)


def test_read_content_of_old_json_is_none():
    assert (
        read_content(SummaryVersion(id=uuid.uuid4(), content={"narrative": 5})) is None
    )


# GET /seniors/{id}/summary (design §5 B, 04 §1)

DAS, MEDIC, OTHER_MEDIC = "+40700000001", "+40700000002", "+40700000003"
CAREGIVER = "+40700000004"


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def briefed(db, add_user, add_senior):
    """Maria past draft with a summary; her medic, a caregiver, herself, DAS, another medic."""
    await add_user(DAS, Role.das)
    await add_user(OTHER_MEDIC, Role.medic)
    medic = await add_user(MEDIC, Role.medic)
    maria = await add_senior(
        SENIOR, medic=medic, enrollment_state=EnrollmentState.accepted
    )
    caregiver, herself = await add_user(CAREGIVER), await add_user(SENIOR)
    db.add_all(
        [
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=maria.id),
            Grant(user_id=herself.id, role=Role.senior, senior_id=maria.id),
        ]
    )
    call_id = await add_call(db, maria)
    add_summary(
        db,
        senior_id=maria.id,
        call_id=call_id,
        previous_id=None,
        content=content("Doamna Maria doarme prost."),
        model="m",
    )
    await db.commit()
    return maria


@pytest.mark.parametrize(
    ("token", "status"),
    [
        (MEDIC, 200),
        (DAS, 200),
        (CAREGIVER, 404),
        (SENIOR, 404),
        (OTHER_MEDIC, 404),
    ],
)
async def test_summary_reach(client, briefed, token, status):
    r = await client.get(f"/api/seniors/{briefed.id}/summary", headers=signed_in(token))
    assert r.status_code == status
    if status == 200:
        assert r.json()["content"]["narrative"] == "Doamna Maria doarme prost."
    else:
        assert r.json() == {"detail": {"reason": "not_found"}}


async def test_das_does_not_see_a_drafts_summary(client, db, briefed):
    await db.execute(
        update(Senior)
        .where(Senior.id == briefed.id)
        .values(enrollment_state=EnrollmentState.draft)
    )
    await db.commit()
    r = await client.get(f"/api/seniors/{briefed.id}/summary", headers=signed_in(DAS))
    assert r.status_code == 404


async def test_no_summary_is_204(client, db, briefed):
    await db.execute(delete(SummaryVersion))
    await db.commit()
    r = await client.get(f"/api/seniors/{briefed.id}/summary", headers=signed_in(MEDIC))
    assert r.status_code == 204


async def test_unreadable_content_is_no_summary(client, db, briefed):
    await db.execute(update(SummaryVersion).values(content={"narrative": 1}))
    await db.commit()
    r = await client.get(f"/api/seniors/{briefed.id}/summary", headers=signed_in(MEDIC))
    assert r.status_code == 204
