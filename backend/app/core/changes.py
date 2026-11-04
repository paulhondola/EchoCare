"""What a transaction changed that a phone should hear about (04 §6, 01 §7).

A package notes each change on the session as it writes it. `app.notify` reads the
notes once the session commits and sends the pushes; a rollback drops them, so no push
announces a change the database did not keep. Nothing here sends.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# The notes' key in Session.info, which an AsyncSession shares with its sync session.
KEY = "echocare.changes"


class ChangeKind(StrEnum):
    code = "code"  # the senior's code was written (05 §2), maybe to the same code
    incident_opened = "incident_opened"
    incident_moved = "incident_moved"  # taken or resolved
    call_moved = "call_moved"  # a call rang, was answered or ended (03 §9)
    caregivers = "caregivers"  # a caregiver grant made or removed


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


def take_notes(session: AsyncSession | Session) -> list[Change]:
    """The changes noted since the last commit or rollback, and forgets them."""
    return session.info.pop(KEY, [])
