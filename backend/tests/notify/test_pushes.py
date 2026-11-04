"""Pushes after a commit (04 §6): who hears about what, and that sending never touches
what was written. Firebase is replaced by a fake sender (06 §5)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.changes import Change, ChangeKind, note
from app.models import Grant, PushToken, Role, SeniorStatus
from app.notify import service
from app.notify.service import (
    Audience,
    Push,
    address,
    code_alert,
    deliver,
    drain,
    incident_alert,
    incidents_refresh,
    per_device,
    pushes_for,
    senior_refresh,
)
from app.status.engine import Severity

DAS, MEDIC = "+40700000001", "+40700000002"
SENIOR, CAREGIVER, STRANGER = "+40700000101", "+40700000103", "+40700000109"

S = uuid.UUID(int=1)
I = uuid.UUID(int=2)

EVERYONE = [
    (Audience.caregivers, senior_refresh(S)),
    (Audience.medic, senior_refresh(S)),
    (Audience.senior, senior_refresh(S)),
]


def code(before, after):
    return Change(ChangeKind.code, S, before=before, after=after)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        # The first code, given with consent, alerts nobody
        (code(None, "green"), EVERYONE),
        (
            code("green", "yellow"),
            [(Audience.caregivers, code_alert(S)), (Audience.medic, senior_refresh(S))],
        ),
        (
            code(None, "yellow"),
            [(Audience.caregivers, code_alert(S)), (Audience.medic, senior_refresh(S))],
        ),
        # P5: a second yellow is no follow-up
        (code("yellow", "yellow"), EVERYONE),
        (
            code("yellow", "red"),
            [(Audience.caregivers, code_alert(S)), (Audience.medic, code_alert(S))],
        ),
        (code("red", "red"), EVERYONE),
        (code("red", "green"), EVERYONE),
        (
            Change(ChangeKind.incident_opened, S, I),
            [(Audience.das, incident_alert(S, I))],
        ),
        (
            Change(ChangeKind.incident_moved, S, I),
            [(Audience.das, incidents_refresh(I))],
        ),
        (Change(ChangeKind.call_moved, S), EVERYONE),
        (Change(ChangeKind.caregivers, S), [(Audience.medic, senior_refresh(S))]),
    ],
)
def test_who_hears_about_each_change(change, expected):
    assert pushes_for(change) == expected


def test_no_message_names_the_senior_or_the_code():
    """P18: ids and a type, nothing a lock screen could leak."""
    for push in (
        code_alert(S),
        incident_alert(S, I),
        senior_refresh(S),
        incidents_refresh(I),
    ):
        assert {k for k, _ in push.data} <= {"type", "what", "senior_id", "incident_id"}
        assert not {"green", "yellow", "red"} & {v for _, v in push.data}


def test_an_alert_stands_in_for_the_refresh_about_the_same_senior():
    other = uuid.UUID(int=3)
    out = per_device(
        {
            "t1": {code_alert(S), senior_refresh(S), senior_refresh(other)},
            "t2": {senior_refresh(S)},
        }
    )
    assert out == [
        ("t1", code_alert(S)),
        ("t1", senior_refresh(other)),
        ("t2", senior_refresh(S)),
    ]


class FakeSender:
    """Records what would go to Firebase; `dead` tokens come back as unregistered."""

    def __init__(self, dead=(), fail=False):
        self.sent: list[tuple[str, Push]] = []
        self.dead = list(dead)
        self.fail = fail

    def send(self, outgoing):
        if self.fail:
            raise RuntimeError("Firebase is down")
        self.sent += outgoing
        return [t for t, _ in outgoing if t in self.dead]

    def by_token(self):
        return {(t, p.alert, dict(p.data).get("type")) for t, p in self.sent}


@pytest.fixture
def sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr(service, "_sender", fake)
    return fake


@pytest.fixture
async def cast(db, add_user, add_active_senior):
    """A senior with her medic and a caregiver, a DAS employee and a stranger, each
    signed in on one device named after their role."""
    das = await add_user(DAS, Role.das, name="DAS Test")
    medic = await add_user(MEDIC, Role.medic)
    senior = await add_active_senior(SENIOR, medic=medic)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    stranger = await add_user(STRANGER, Role.medic)
    owner = await db.scalar(
        select(Grant.user_id).where(
            Grant.senior_id == senior.id, Grant.role == Role.senior
        )
    )
    for token, user in [
        ("das", das.id),
        ("medic", medic.id),
        ("senior", owner),
        ("caregiver", caregiver.id),
        ("stranger", stranger.id),
    ]:
        db.add(PushToken(user_id=user, token=token))
    await db.commit()
    return senior


async def test_a_yellow_alerts_the_caregiver_and_refreshes_the_medic(db, cast):
    out = await address(db, [Change(ChangeKind.code, cast.id, None, "green", "yellow")])
    assert out == [
        ("caregiver", code_alert(cast.id)),
        ("medic", senior_refresh(cast.id)),
    ]


async def test_a_red_with_its_incident_alerts_caregiver_medic_and_das(db, cast):
    out = await address(
        db,
        [
            Change(ChangeKind.code, cast.id, None, "yellow", "red"),
            Change(ChangeKind.incident_opened, cast.id, I),
            Change(ChangeKind.call_moved, cast.id),
        ],
    )
    assert out == [
        ("caregiver", code_alert(cast.id)),
        ("das", incident_alert(cast.id, I)),
        ("medic", code_alert(cast.id)),
        # The senior's own app has no alert to stand in for its refresh
        ("senior", senior_refresh(cast.id)),
    ]


async def test_a_medic_who_lost_the_grant_hears_nothing(db, cast):
    await db.execute(Grant.__table__.delete().where(Grant.role == Role.medic))
    await db.commit()
    out = await address(db, [Change(ChangeKind.caregivers, cast.id)])
    assert out == []


async def test_a_mock_answer_ending_yellow_alerts_the_caregiver(
    client, db, cast, sender, monkeypatch
):
    """The issue's done-when, through the API: the caregiver's phone gets the alert and
    nobody's push names her or her code."""
    monkeypatch.setattr(
        "app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15)
    )
    das = {"Authorization": f"Bearer {DAS}"}
    r = await client.post(
        "/api/campaigns", json={"kind": "cold", "level": "yellow"}, headers=das
    )
    assert r.status_code == 201
    me = {"Authorization": f"Bearer {SENIOR}"}
    call_id = (await client.get("/api/profile/mock-call", headers=me)).json()["call_id"]
    await drain()
    sender.sent.clear()  # the campaign's queueing is no news

    r = await client.post(
        f"/api/calls/{call_id}/mock-answer",
        json={"feeling": "unwell", "day": "joi", "shelter": "yes"},
        headers=me,
    )
    assert r.status_code == 204
    await drain()
    assert (
        await db.scalar(
            select(SeniorStatus.code).where(SeniorStatus.senior_id == cast.id)
        )
        is Severity.yellow
    )
    assert sender.by_token() == {
        ("caregiver", True, "code_changed"),
        ("medic", False, "refresh"),
        ("senior", False, "refresh"),
    }


async def test_nothing_is_sent_for_a_rollback(db, cast, sender):
    await db.execute(select(1))  # a note follows a write, inside its transaction
    note(db, Change(ChangeKind.caregivers, cast.id))
    await db.rollback()
    await db.commit()
    await drain()
    assert sender.sent == []


async def test_a_commit_sends_what_its_transaction_noted(db, cast, sender):
    note(db, Change(ChangeKind.caregivers, cast.id))
    await db.commit()
    await drain()
    assert sender.sent == [("medic", senior_refresh(cast.id))]


async def test_a_dead_token_is_dropped(db, cast):
    await deliver([Change(ChangeKind.caregivers, cast.id)], FakeSender(dead=["medic"]))
    tokens = set(await db.scalars(select(PushToken.token)))
    assert tokens == {"das", "senior", "caregiver", "stranger"}


async def test_a_failed_send_changes_nothing(db, cast, caplog):
    before = set(await db.scalars(select(PushToken.token)))
    await deliver([Change(ChangeKind.caregivers, cast.id)], FakeSender(fail=True))
    assert set(await db.scalars(select(PushToken.token))) == before
    assert "pushes for 1 changes failed" in caplog.text
