"""Exporting a senior's data through each table's owner (design 2026-11-14, ADR-005)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, Role, User
from app.auth.service import Caller
from app.codes.models import ReportSource, SeniorStatus, StatusReport
from app.core.db import Base
from app.core.storage import StorageService
from app.export.service import export_senior
from app.incidents.models import (
    Event,
    EventType,
    Incident,
    IncidentOutcome,
    IncidentStatus,
)
from app.medical.models import MedicalRecord, MedicalRecordState
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    Senior,
    SummaryVersion,
    WatchCondition,
    WatchReading,
    WatchState,
)
from app.status.engine import Certainty, Question, Severity
from app.voice.calls import CallState
from app.voice.models import Answer, Call, CallTrigger, CallTurn, Speaker, TurnKind

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


class FakeStorage(StorageService):
    def __init__(self, url: str = "https://files.test/record.pdf") -> None:
        self.url = url

    async def generate_presigned_url(self, key: str, expires_in: int = 600) -> str:
        return f"{self.url}?key={key}"


async def caller_for(db: AsyncSession, user: User) -> Caller:
    grants = list(await db.scalars(select(Grant).where(Grant.user_id == user.id)))
    return Caller(user, grants)


def add_call(db: AsyncSession, senior: Senior, **columns) -> Call:
    call = Call(
        senior_id=senior.id,
        trigger=columns.pop("trigger", CallTrigger.campaign),
        starting_severity=Severity.green,
        state=columns.pop("state", CallState.completed),
        due_at=columns.pop("due_at", NOW),
        **columns,
    )
    db.add(call)
    return call


@pytest.fixture
async def das(add_user) -> User:
    return await add_user("+40700000001", Role.das, name="Dispecer")


async def add_caregiver(db: AsyncSession, add_user, senior: Senior, phone: str) -> User:
    user = await add_user(phone, name="Ion Pop")
    db.add(
        Grant(
            user_id=user.id,
            role=Role.caregiver,
            senior_id=senior.id,
            relation="fiu",
            granted_by=senior.medic_id,
        )
    )
    await db.commit()
    return user


async def test_export_includes_every_senior_row(
    db: AsyncSession, add_user, add_active_senior, das: User
):
    senior = await add_active_senior("+40700000101")
    caregiver = await add_caregiver(db, add_user, senior, "+40700000201")
    first = add_call(
        db,
        senior,
        due_at=NOW - timedelta(hours=2),
        twilio_call_id="CA123",
        dialed_at=NOW - timedelta(hours=2),
    )
    await db.flush()
    second = add_call(db, senior, previous_call_id=first.id, due_at=NOW)
    await db.flush()
    event_id = uuid.uuid4()
    db.add_all(
        [
            Consent(
                senior_id=senior.id,
                decision=ConsentDecision.given,
                method=ConsentMethod.call,
                text_version="v2",
                call_id=first.id,
                evidence={"speech": "Da.", "confidence": 0.95},
                at=NOW,
            ),
            SummaryVersion(
                senior_id=senior.id,
                call_id=second.id,
                content={"narrative": "ok"},
                model="m",
                created_at=NOW,
            ),
            WatchState(
                senior_id=senior.id,
                state=WatchCondition.ok,
                last_check_in_at=NOW,
                last_pulse=72,
            ),
            WatchReading(
                senior_id=senior.id,
                measured_at=NOW - timedelta(hours=1),
                pulse=70,
                resting_pulse=62,
                steps_today=1200,
                battery=85,
                worn=True,
            ),
            WatchReading(
                senior_id=senior.id,
                measured_at=NOW,
                pulse=72,
                resting_pulse=62,
                steps_today=1500,
                battery=84,
                worn=True,
            ),
            Event(
                id=event_id,
                senior_id=senior.id,
                type=EventType.fall,
                source="watch",
                measured_at=NOW,
                received_at=NOW,
                snapshot={"g": 3.2},
                latitude=45.75,
                longitude=21.22,
                location_accuracy_m=10.5,
                located_at=NOW,
                call_id=first.id,
            ),
            Incident(
                senior_id=senior.id,
                status=IncidentStatus.resolved,
                reason="Cădere",
                opened_by_call_id=first.id,
                opened_at=NOW,
                outcome=IncidentOutcome.senior_ok,
                note="Totul în regulă.",
                resolved_by=das.id,
                resolved_at=NOW,
            ),
            CallTurn(
                call_id=first.id,
                position=0,
                speaker=Speaker.senior,
                kind=TurnKind.speech,
                content="Bine.",
                confidence=0.91,
                at=NOW,
            ),
            Answer(
                call_id=first.id,
                field=Question.feeling,
                value="bine",
                clear=True,
                quote="Bine.",
                at=NOW,
            ),
            StatusReport(
                call_id=second.id,
                source=ReportSource.rules,
                severity=Severity.green,
                certainty=Certainty.high,
                reason="r",
                quote="Bine.",
                at=NOW,
            ),
            SeniorStatus(
                senior_id=senior.id,
                code=Severity.green,
                reason="r",
                since=NOW,
                source_call_id=second.id,
            ),
            MedicalRecord(
                senior_id=senior.id,
                storage_key=f"medical-records/{senior.id}/x.pdf",
                uploaded_by=senior.medic_id,
                state=MedicalRecordState.confirmed,
                source_text="Text intern confidențial",
                items=[
                    {
                        "condition": "HTA",
                        "question": "Ați luat pastila?",
                        "worrying": "Nu",
                        "evidence": "HTA",
                        "included": True,
                    }
                ],
                confirmed_at=NOW,
                confirmed_by=senior.medic_id,
            ),
        ]
    )
    await db.commit()

    exported = await export_senior(
        db, await caller_for(db, das), senior.id, FakeStorage()
    )
    dumped = exported.model_dump(mode="json")

    assert exported.senior.id == senior.id
    assert [c.user_id for c in exported.senior.caregivers] == [caregiver.id]
    assert exported.status is not None
    assert exported.status.code == "green"
    assert exported.status.source_call_id == second.id
    assert len(exported.consents) == 1
    assert exported.consents[0].evidence == {"speech": "Da.", "confidence": 0.95}
    assert len(exported.summaries) == 1
    assert exported.summaries[0].content == {"narrative": "ok"}
    assert exported.watch.state is not None
    assert exported.watch.state.last_pulse == 72
    assert [r.pulse for r in exported.watch.readings] == [70, 72]
    assert [r.resting_pulse for r in exported.watch.readings] == [62, 62]
    assert len(exported.events) == 1
    assert exported.events[0].id == event_id
    assert exported.events[0].latitude == 45.75
    assert len(exported.incidents) == 1
    assert exported.incidents[0].outcome == "senior_ok"
    assert exported.incidents[0].note == "Totul în regulă."
    assert [c.id for c in exported.calls] == [first.id, second.id]
    assert exported.calls[0].turns[0].content == "Bine."
    assert exported.calls[0].answers[0].quote == "Bine."
    assert exported.calls[1].reports[0].severity == "green"
    assert exported.calls[1].reports[0].certainty == "high"
    assert exported.medical_record is not None
    assert exported.medical_record.state == MedicalRecordState.confirmed
    assert len(exported.medical_record.items) == 1
    assert exported.medical_record.pdf_url.endswith(
        f"key=medical-records/{senior.id}/x.pdf"
    )

    raw_text = str(dumped)
    for forbidden in (
        "source_text",
        "Text intern confidențial",
        "storage_key",
        "twilio_call_id",
        "CA123",
        "dialed_at",
        "firebase_uid",
    ):
        assert forbidden not in raw_text, forbidden


async def test_export_redacts_unconfirmed_medical_record_for_das_but_not_medic(
    db: AsyncSession, add_active_senior, das: User
):
    senior = await add_active_senior("+40700000101")
    medic = await db.get(User, senior.medic_id)
    db.add(
        MedicalRecord(
            senior_id=senior.id,
            storage_key=f"medical-records/{senior.id}/x.pdf",
            uploaded_by=senior.medic_id,
            state=MedicalRecordState.review,
            items=[
                {
                    "condition": "HTA",
                    "question": "Ați luat pastila?",
                    "worrying": "Nu",
                    "evidence": "HTA",
                    "included": True,
                }
            ],
        )
    )
    await db.commit()

    by_medic = await export_senior(
        db, await caller_for(db, medic), senior.id, FakeStorage()
    )
    assert by_medic.medical_record is not None
    assert by_medic.medical_record.items is not None
    assert by_medic.medical_record.pdf_url is not None

    by_das = await export_senior(
        db, await caller_for(db, das), senior.id, FakeStorage()
    )
    assert by_das.medical_record is not None
    assert by_das.medical_record.state == MedicalRecordState.review
    assert by_das.medical_record.items is None
    assert by_das.medical_record.pdf_url is None


async def test_export_refuses_das_on_draft(db: AsyncSession, add_senior, das: User):
    """A draft is out of DAS's reach (01 §6), so it answers 404 not_found."""
    senior = await add_senior("+40700000101")
    with pytest.raises(HTTPException) as refused:
        await export_senior(db, await caller_for(db, das), senior.id, FakeStorage())
    assert refused.value.status_code == 404
    assert refused.value.detail == {"reason": "not_found"}


async def test_export_refuses_caregiver(db: AsyncSession, add_user, add_active_senior):
    """A caregiver reaches the senior, so editable_senior answers 403 not_allowed."""
    senior = await add_active_senior("+40700000101")
    caregiver = await add_caregiver(db, add_user, senior, "+40700000201")
    with pytest.raises(HTTPException) as refused:
        await export_senior(
            db, await caller_for(db, caregiver), senior.id, FakeStorage()
        )
    assert refused.value.status_code == 403
    assert refused.value.detail == {"reason": "not_allowed"}


# Every table besides `seniors` that points at a senior or a call, or names one by
# column. A new one fails here until export_senior reads its rows and this list names it.
EXPORTED_TABLES = {
    "grants",
    "consents",
    "senior_summaries",
    "watch_states",
    "watch_readings",
    "home_node_states",
    "events",
    "incidents",
    "calls",
    "call_turns",
    "answers",
    "status_reports",
    "senior_statuses",
    "medical_records",
    "health_readings",  # shortcut: read in Task 3
}


def test_every_senior_table_is_exported():
    about_a_senior = {
        table.name
        for table in Base.metadata.sorted_tables
        if {"senior_id", "call_id"} & set(table.columns.keys())
        or any(
            fk.column.table.name in ("seniors", "calls") for fk in table.foreign_keys
        )
    }
    assert about_a_senior == EXPORTED_TABLES
