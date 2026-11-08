"""The senior_summaries versions: one per call, newest wins (#63, design §4)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.models import Call, SummaryVersion
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
