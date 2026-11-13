"""Pushes after a commit (04 §6): who hears about what, and that sending never touches
what was written. Firebase is replaced by a fake sender (06 §5)."""

import asyncio
import json
import threading
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import firebase_admin
import pytest
from firebase_admin import messaging
from firebase_admin.exceptions import InvalidArgumentError
from sqlalchemy import select

from app.calls.ending import begin_handover
from app.codes.models import ReportSource
from app.core.changes import Change, ChangeKind, note
from app.models import (
    Call,
    CallTrigger,
    Grant,
    Incident,
    IncidentStatus,
    PushToken,
    Role,
    SeniorStatus,
    WatchState,
)
from app.notify import service
from app.notify.service import (
    ALERT_CHANNEL,
    ALERT_TEXT,
    DELIVERIES,
    Audience,
    FirebaseSender,
    Push,
    address,
    code_alert,
    deliver,
    drain,
    incident_alert,
    incidents_refresh,
    medical_notice,
    message,
    per_device,
    pushes_for,
    sender_from,
    senior_refresh,
)
from app.seniors.models import WatchCondition
from app.seniors.schemas import CheckInForm
from app.seniors.service import record_check_in, silence_watches
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.service import move_call

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
        (
            Change(ChangeKind.incident_raised, S, I),
            [(Audience.das, incident_alert(S, I))],
        ),
        (Change(ChangeKind.call_moved, S), EVERYONE),
        (Change(ChangeKind.watch, S), EVERYONE),
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


def wire(push: Push) -> dict:
    """The message as Firebase receives it."""
    return messaging._MessagingService.encode_message(message("t", push))


def test_an_alert_shows_on_the_alerts_channel_at_high_priority():
    sent = wire(code_alert(S))
    assert sent["notification"] == {"title": "EchoCare", "body": ALERT_TEXT}
    assert sent["android"]["priority"] == "high"
    assert sent["android"]["notification"]["channel_id"] == ALERT_CHANNEL
    assert sent["data"] == {"type": "code_changed", "senior_id": str(S)}


def test_a_refresh_is_silent_and_never_waits_at_firebase():
    """A stored refresh is worth nothing, and past 100 stored messages for a device
    Firebase discards them all, alerts included."""
    sent = wire(senior_refresh(S))
    assert "notification" not in sent
    assert sent["android"]["priority"] == "normal"
    assert sent["android"]["ttl"] == "0s"


def answered(*outcomes):
    return SimpleNamespace(
        responses=[SimpleNamespace(success=o is None, exception=o) for o in outcomes]
    )


@pytest.mark.parametrize(
    ("error", "dead"),
    [
        (None, False),
        (messaging.UnregisteredError("gone"), True),
        (messaging.SenderIdMismatchError("other project"), True),
        (
            InvalidArgumentError(
                "The registration token is not a valid FCM registration token"
            ),
            True,
        ),
        # A fault in the message itself must not cost every device its token
        (InvalidArgumentError("Message payload too large"), False),
        (messaging.QuotaExceededError("slow down"), False),
    ],
)
def test_which_answers_mean_the_token_is_dead(monkeypatch, error, dead):
    monkeypatch.setattr(messaging, "send_each", lambda *_, **__: answered(error))
    sender = FirebaseSender.__new__(FirebaseSender)
    sender._app = None
    assert sender.send([("t", senior_refresh(S))]) == (["t"] if dead else [])


def test_no_credential_means_no_sender():
    assert sender_from("") is None


def test_a_credential_makes_a_sender_with_the_messaging_scope():
    raw = {
        "type": "authorized_user",
        "client_id": "c",
        "client_secret": "s",
        "refresh_token": "r",
    }
    sender = sender_from(json.dumps(raw))
    try:
        assert sender._app.project_id
        assert sender._app.credential.get_credential().scopes == service.SCOPES
    finally:
        firebase_admin.delete_app(sender._app)


def live_call(senior, trigger=CallTrigger.campaign):
    return Call(
        senior_id=senior.id,
        trigger=trigger,
        starting_severity=Severity.yellow,
        due_at=datetime.now(UTC),
        state=CallState.in_progress,
    )


async def with_incident(db, senior, code):
    """A hand-over's incident still open, and the code it left."""
    earlier = live_call(senior)
    earlier.state = CallState.handed_over
    db.add(earlier)
    await db.flush()
    db.add(
        Incident(
            senior_id=senior.id,
            status=IncidentStatus.open,
            opened_by_call_id=earlier.id,
            reason="Predare",
        )
    )
    db.add(
        SeniorStatus(
            senior_id=senior.id,
            code=code,
            reason="Predare",
            since=datetime.now(UTC),
        )
    )
    call = live_call(senior)
    db.add(call)
    await db.commit()
    return call


async def test_a_red_joining_an_open_incident_alerts_das(db, cast, sender):
    """G16 adds it to the incident, so none opens; 04 §6 still tells every DAS phone."""
    call = await with_incident(db, cast, Severity.yellow)
    assert await begin_handover(call.id, ReportSource.alarm_tier1, "Alarmă")
    await drain()
    assert ("das", True, "incident") in sender.by_token()


async def test_a_red_that_was_red_already_tells_das_nothing_new(db, cast, sender):
    call = await with_incident(db, cast, Severity.red)
    assert await begin_handover(call.id, ReportSource.alarm_tier1, "Alarmă")
    await drain()
    assert "das" not in {token for token, _, _ in sender.by_token()}


async def test_a_scripted_test_call_tells_nobody(db, cast, sender):
    """05 §1: a test call counts for no rule, and the history leaves it out."""
    call = live_call(cast, CallTrigger.test)
    db.add(call)
    await db.commit()
    await move_call(db, call.id, None, CallState.completed)
    await drain()
    assert sender.sent == []


def check_in(worn, at):
    return CheckInForm(measured_at=at, worn=worn)


async def test_a_watch_that_changes_state_refreshes_everyone(db, cast, sender):
    now = datetime.now(UTC)
    await record_check_in(db, cast.id, check_in(True, now), now)
    await drain()
    sender.sent.clear()

    later = now + timedelta(minutes=1)
    await record_check_in(db, cast.id, check_in(False, later), later)
    await drain()
    assert sender.by_token() == {
        ("caregiver", False, "refresh"),
        ("medic", False, "refresh"),
        ("senior", False, "refresh"),
    }


async def test_a_check_in_in_the_same_state_tells_nobody(db, cast, sender):
    now = datetime.now(UTC)
    await record_check_in(db, cast.id, check_in(True, now), now)
    await drain()
    sender.sent.clear()

    later = now + timedelta(minutes=1)
    await record_check_in(db, cast.id, check_in(True, later), later)
    await drain()
    assert sender.sent == []


async def test_a_watch_going_silent_refreshes_everyone(db, cast, sender):
    now = datetime.now(UTC)
    db.add(
        WatchState(
            senior_id=cast.id,
            state=WatchCondition.ok,
            last_check_in_at=now - timedelta(days=1),
        )
    )
    await db.commit()
    assert await silence_watches(db, now) == 1
    await drain()
    assert ("caregiver", False, "refresh") in sender.by_token()


async def test_a_savepoint_released_sends_nothing_until_the_commit(db, cast, sender):
    async with db.begin_nested():
        note(db, Change(ChangeKind.caregivers, cast.id))
    await drain()
    assert sender.sent == []
    await db.commit()
    await drain()
    assert sender.sent == [("medic", senior_refresh(cast.id))]


async def test_a_savepoint_rolled_back_takes_only_its_own_notes(db, cast, sender):
    note(db, Change(ChangeKind.caregivers, cast.id))
    savepoint = await db.begin_nested()
    note(db, Change(ChangeKind.code, cast.id, None, "green", "red"))
    await savepoint.rollback()
    await db.commit()
    await drain()
    assert sender.sent == [("medic", senior_refresh(cast.id))]


class SlowSender(FakeSender):
    """Counts how many sends run at once."""

    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self.running = 0
        self.most = 0

    def send(self, outgoing):
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        time.sleep(0.05)
        with self.lock:
            self.running -= 1
        return super().send(outgoing)


async def test_a_burst_of_commits_delivers_a_few_at_a_time(db, cast, monkeypatch):
    """Deliveries share the pool with the requests, Twilio's callbacks among them."""
    slow = SlowSender()
    monkeypatch.setattr(service, "_sender", slow)
    # A semaphore that has made anyone wait belongs to that test's event loop
    monkeypatch.setattr(service, "_in_turn", asyncio.Semaphore(DELIVERIES))
    for _ in range(DELIVERIES * 3):
        note(db, Change(ChangeKind.caregivers, cast.id))
        await db.commit()
    await asyncio.wait_for(drain(), timeout=10)
    assert len(slow.sent) == DELIVERIES * 3
    assert slow.most <= DELIVERIES


def test_a_ready_record_notifies_the_medic_only():
    assert pushes_for(Change(ChangeKind.medical_record, S)) == [
        (Audience.medic, medical_notice(S))
    ]


def test_a_notice_is_visible_on_the_updates_channel():
    m = message("t", medical_notice(S))
    assert m.notification.body == "O fișă medicală e gata de verificat."
    assert m.android.priority == "normal"
    assert m.android.notification.channel_id == "updates"
    assert dict(m.data) == {"type": "medical_record", "senior_id": str(S)}
