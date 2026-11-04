"""Pushes to the Android apps after a commit (04 §6, 01 §7, G4).

`install` hooks every session. Once one commits, the changes its packages noted
(`app.core.changes`) become pushes, sent in a task of their own: a request never waits
on Firebase, and a failed send changes nothing that was written. A rollback drops the
notes. Messages carry no name, no code and no reason (P18); the app reads those from
the API. A lost push is caught by the screen's timed re-read (06 §1).
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import batched
from typing import Any, Protocol

import firebase_admin
import google.auth
import google.auth.credentials
from firebase_admin import credentials, messaging
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import SessionTransaction

from app.auth.models import Grant, PushToken, Role
from app.auth.service import FIREBASE_PROJECT_ID, drop_dead_tokens
from app.core.changes import Change, ChangeKind, take_notes
from app.core.db import Session
from app.seniors.models import Senior

log = logging.getLogger("echocare.notify")

# The visible notification of every alert (04 §6), in Romanian.
ALERT_TITLE = "EchoCare"
ALERT_TEXT = "O persoană pe care o urmăriți are nevoie de atenție."
# The Android app's channel for alerts (android/app: Push.kt), created at its start.
ALERT_CHANNEL = "alerts"
# Firebase sends at most this many messages in one call.
BATCH = 500
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


class Audience(StrEnum):
    caregivers = "caregivers"  # the senior's caregivers
    medic = "medic"  # the medic who registered the senior
    senior = "senior"  # the senior's own app
    das = "das"  # every DAS employee


@dataclass(frozen=True)
class Push:
    """One message before it is addressed. `data` is a tuple so equal pushes are one."""

    alert: bool
    data: tuple[tuple[str, str], ...]

    def ids(self) -> set[str]:
        return {v for k, v in self.data if k in ("senior_id", "incident_id")}


def code_alert(senior_id: uuid.UUID) -> Push:
    return Push(True, (("type", "code_changed"), ("senior_id", str(senior_id))))


def incident_alert(senior_id: uuid.UUID, incident_id: uuid.UUID) -> Push:
    return Push(
        True,
        (
            ("type", "incident"),
            ("senior_id", str(senior_id)),
            ("incident_id", str(incident_id)),
        ),
    )


def senior_refresh(senior_id: uuid.UUID) -> Push:
    return Push(
        False, (("type", "refresh"), ("what", "senior"), ("senior_id", str(senior_id)))
    )


def incidents_refresh(incident_id: uuid.UUID) -> Push:
    return Push(
        False,
        (("type", "refresh"), ("what", "incidents"), ("incident_id", str(incident_id))),
    )


def pushes_for(change: Change) -> list[tuple[Audience, Push]]:
    """Who hears about one change, and how: 04 §6's recipients table.

    Only a code that moves into yellow or red alerts; the same code again, from a
    later call, is a refresh, since P5 has no follow-up. Every incident that opens
    alerts DAS, a yellow hand-over's included (UC-07): each one waits for a dispatcher.
    """
    senior = change.senior_id
    refresh = senior_refresh(senior)
    everyone = [
        (Audience.caregivers, refresh),
        (Audience.medic, refresh),
        (Audience.senior, refresh),
    ]
    match change.kind:
        case ChangeKind.code if change.after == change.before:
            return everyone
        case ChangeKind.code if change.after == "yellow":
            return [
                (Audience.caregivers, code_alert(senior)),
                (Audience.medic, refresh),
            ]
        case ChangeKind.code if change.after == "red":
            alert = code_alert(senior)
            return [(Audience.caregivers, alert), (Audience.medic, alert)]
        case ChangeKind.code | ChangeKind.call_moved:
            return everyone
        case ChangeKind.incident_opened if change.incident_id is not None:
            return [(Audience.das, incident_alert(senior, change.incident_id))]
        case ChangeKind.incident_moved if change.incident_id is not None:
            return [(Audience.das, incidents_refresh(change.incident_id))]
        case ChangeKind.caregivers:
            return [(Audience.medic, refresh)]
    return []


def per_device(wanted: dict[str, set[Push]]) -> list[tuple[str, Push]]:
    """Each device's pushes, an alert standing in for the refreshes about the same
    senior or incident: opening it reads them anyway. Sorted, so a send is repeatable."""
    out = []
    for token, pushes in wanted.items():
        alerted = set().union(*(p.ids() for p in pushes if p.alert))
        out += [(token, p) for p in pushes if p.alert or not (p.ids() & alerted)]
    return sorted(out, key=lambda tp: (tp[0], not tp[1].alert, tp[1].data))


async def audience(
    session: AsyncSession, who: Audience, senior_id: uuid.UUID
) -> set[uuid.UUID]:
    """The users `who` names for this senior, by their grants (01 §6)."""
    match who:
        case Audience.caregivers | Audience.senior:
            role = Role.caregiver if who is Audience.caregivers else Role.senior
            query = select(Grant.user_id).where(
                Grant.senior_id == senior_id, Grant.role == role
            )
        case Audience.medic:
            # Only while they still hold the medic grant: that is what reaches her (AL2)
            query = (
                select(Senior.medic_id)
                .join(Grant, Grant.user_id == Senior.medic_id)
                .where(Senior.id == senior_id, Grant.role == Role.medic)
            )
        case Audience.das:
            query = select(Grant.user_id).where(Grant.role == Role.das)
    return set(await session.scalars(query))


async def address(
    session: AsyncSession, changes: Iterable[Change]
) -> list[tuple[str, Push]]:
    """Every (token, push) the changes call for, on every device of every recipient."""
    users: dict[tuple[Audience, uuid.UUID], set[uuid.UUID]] = {}
    wanted_by_user: dict[uuid.UUID, set[Push]] = {}
    for change in changes:
        for who, push in pushes_for(change):
            key = (who, change.senior_id)
            if key not in users:
                users[key] = await audience(session, who, change.senior_id)
            for user in users[key]:
                wanted_by_user.setdefault(user, set()).add(push)
    if not wanted_by_user:
        return []
    tokens = await session.execute(
        select(PushToken.token, PushToken.user_id).where(
            PushToken.user_id.in_(wanted_by_user)
        )
    )
    wanted: dict[str, set[Push]] = {}
    for token, user in tokens:
        wanted.setdefault(token, set()).update(wanted_by_user[user])
    return per_device(wanted)


def message(token: str, push: Push) -> messaging.Message:
    """An alert shows the notification, on the alerts channel, also when the app is
    closed; a refresh is data only and wakes nobody (04 §6)."""
    if push.alert:
        return messaging.Message(
            token=token,
            data=dict(push.data),
            notification=messaging.Notification(title=ALERT_TITLE, body=ALERT_TEXT),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(channel_id=ALERT_CHANNEL),
            ),
        )
    return messaging.Message(
        token=token,
        data=dict(push.data),
        android=messaging.AndroidConfig(priority="normal"),
    )


class Sender(Protocol):
    def send(self, outgoing: list[tuple[str, Push]]) -> list[str]:
        """Sends; returns the tokens Firebase says no longer reach a device. Blocks."""
        ...


class _Credential(credentials.Base):
    """Any Google credential the JSON describes: a service account key, or a keyless
    workload identity configuration (auth-layer AL11)."""

    def __init__(self, info: dict[str, Any]) -> None:
        self._google, _ = google.auth.load_credentials_from_dict(info, scopes=SCOPES)

    def get_credential(self) -> google.auth.credentials.Credentials:
        return self._google


class FirebaseSender:
    """Firebase Cloud Messaging through the Admin SDK, as its own app: the sign-in app
    holds no credential (AL11)."""

    def __init__(self, info: dict[str, Any]) -> None:
        self._app = firebase_admin.initialize_app(
            _Credential(info), {"projectId": FIREBASE_PROJECT_ID}, name="push"
        )

    def send(self, outgoing: list[tuple[str, Push]]) -> list[str]:
        dead = []
        for chunk in batched(outgoing, BATCH):
            sent = messaging.send_each([message(*o) for o in chunk], app=self._app)
            for (token, _), answer in zip(chunk, sent.responses, strict=True):
                if answer.success:
                    continue
                if isinstance(
                    answer.exception,
                    messaging.UnregisteredError | messaging.SenderIdMismatchError,
                ):
                    dead.append(token)
                else:
                    log.warning("push failed: %s", type(answer.exception).__name__)
        return dead


def sender_from(raw: str) -> Sender | None:
    """The sender for FIREBASE_PUSH_CREDENTIALS; none when it is empty, as locally."""
    if not raw:
        log.info("no FIREBASE_PUSH_CREDENTIALS: pushes are not sent")
        return None
    return FirebaseSender(json.loads(raw))


async def deliver(changes: list[Change], sender: Sender) -> None:
    """Addresses and sends the changes' pushes, then forgets dead tokens. Never raises:
    the change is written already (06 §1)."""
    try:
        async with Session() as session:
            outgoing = await address(session, changes)
        if not outgoing:
            return
        dead = await asyncio.to_thread(sender.send, outgoing)
        log.info("sent %d pushes, %d tokens dead", len(outgoing), len(dead))
        if dead:
            async with Session() as session:
                await drop_dead_tokens(session, dead)
                await session.commit()
    except Exception:
        log.exception("pushes for %d changes failed", len(changes))


_sender: Sender | None = None
# Running deliveries, kept so a task is not collected before it ends.
_tasks: set[asyncio.Task[None]] = set()


def _after_commit(session: OrmSession) -> None:
    changes = take_notes(session)
    if not changes or _sender is None:
        return
    try:
        task = asyncio.get_running_loop().create_task(deliver(changes, _sender))
    except RuntimeError:
        log.warning("no event loop: %d changes not pushed", len(changes))
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _after_rollback(session: OrmSession, previous: SessionTransaction) -> None:
    # Every rollback() call, even with nothing sent to the database yet; a savepoint's
    # rollback leaves the outer transaction's notes.
    if not previous.nested:
        take_notes(session)


def install(sender: Sender | None) -> None:
    """Sends pushes after every commit from now on; repeat-safe."""
    global _sender
    _sender = sender
    for name, listener in (
        ("after_commit", _after_commit),
        ("after_soft_rollback", _after_rollback),
    ):
        if not event.contains(OrmSession, name, listener):
            event.listen(OrmSession, name, listener)


async def drain() -> None:
    """Waits for the deliveries under way: tests, and a clean shutdown."""
    while _tasks:
        await asyncio.gather(*_tasks)
