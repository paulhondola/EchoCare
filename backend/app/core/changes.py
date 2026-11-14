"""What a transaction changed that a phone should hear about (04 §6, 01 §7).

A package notes each change on the session as it writes it. `app.notify` reads the
notes once the session commits and sends the pushes; a rollback drops them, so no push
announces a change the database did not keep. A savepoint's rollback drops only the notes
made since it began. Nothing here sends.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

# The notes' key in Session.info, which an AsyncSession shares with its sync session.
KEY = "echocare.changes"
# How many notes each savepoint found when it began.
MARKS = "echocare.change_marks"


class ChangeKind(StrEnum):
    code = "code"  # the senior's code was written (05 §2), maybe to the same code
    incident_opened = "incident_opened"
    incident_raised = "incident_raised"  # a red joined an unresolved incident (G16)
    incident_moved = "incident_moved"  # taken or resolved
    call_moved = "call_moved"  # a call rang, was answered or ended (03 §9)
    caregivers = "caregivers"  # a caregiver grant made or removed
    watch = "watch"  # the watch's state moved (UC-13)
    home_node = "home_node"  # the home node went offline or came back (UC-13)
    medical_record = "medical_record"  # a record's analysis is ready for review


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    senior_id: uuid.UUID
    incident_id: uuid.UUID | None = None
    # A `code` change's code before and after, by name ("yellow"); none before the first.
    before: str | None = None
    after: str | None = None


def note(session: AsyncSession | Session | None, change: Change) -> None:
    """Keeps `change` for after the commit. A row in no session is never written, so
    there is nothing to announce."""
    if session is not None:
        session.info.setdefault(KEY, []).append(change)


def mark_savepoint(session: Session, savepoint: SessionTransaction) -> None:
    """Remembers where `savepoint` began, for `drop_since`."""
    marks = session.info.setdefault(MARKS, {})
    marks[savepoint] = len(session.info.get(KEY, []))


def drop_since(session: Session, savepoint: SessionTransaction) -> None:
    """Forgets the notes made since `savepoint` began: it was rolled back."""
    begun_at = session.info.get(MARKS, {}).pop(savepoint, 0)
    del session.info.get(KEY, [])[begun_at:]


def take_notes(session: AsyncSession | Session) -> list[Change]:
    """The changes noted since the last commit or rollback, and forgets them."""
    session.info.pop(MARKS, None)
    return session.info.pop(KEY, [])
