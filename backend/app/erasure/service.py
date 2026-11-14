"""Erasing a senior and everything stored about them (GDPR Art. 17; design 2026-11-14).

Each table's owner deletes its own rows (ADR-005); this module only orders them,
children first, in one transaction. A wrong order fails on a foreign key and rolls
back, never leaving half a senior.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import (
    Caller,
    drop_users_without_grants,
    grant_holder_ids,
    refuse,
)
from app.codes.service import erase_senior_codes
from app.core.storage import StorageError, StorageService
from app.incidents.service import erase_senior_incidents, incident_unresolved
from app.medical.service import erase_record
from app.seniors.service import (
    editable_senior,
    erase_senior_children,
    erase_senior_row,
    lock_for_erasure,
)
from app.voice.service import call_live, erase_calls, senior_call_ids

log = logging.getLogger("echocare.erasure")


async def erase_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> str | None:
    """Deletes the senior and every row about them, and commits. Returns the medical
    record PDF's key, if any, for the caller to delete from the file store after the
    commit. Refused while a call is live or an incident unresolved; a refusal changes
    nothing."""
    await editable_senior(session, caller, senior_id)  # access
    await lock_for_erasure(session, senior_id)  # no insert for the senior from here on
    if await call_live(session, senior_id):
        log.info("refused call_live: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "call_live")
    if await incident_unresolved(session, senior_id):
        log.info("refused incident_open: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "incident_open")
    call_ids = await senior_call_ids(session, senior_id)
    user_ids = await grant_holder_ids(session, senior_id)
    # Children first: status reports, events, incidents, consents and summaries point
    # at calls; calls and the medical record point at the senior; grants cascade.
    await erase_senior_codes(session, senior_id, call_ids)
    await erase_senior_incidents(session, senior_id)
    await erase_senior_children(session, senior_id)
    await erase_calls(session, call_ids)
    key = await erase_record(session, senior_id)
    await erase_senior_row(session, senior_id)
    await drop_users_without_grants(session, user_ids)
    await session.commit()
    log.info("erased senior %s by user %s", senior_id, caller.user.id)
    return key


async def delete_pdf(storage: StorageService, senior_id: uuid.UUID, key: str) -> None:
    """After the commit: the database is clean either way, so a store that fails
    leaves an orphaned file, named in the log, and the request still succeeds."""
    try:
        await storage.delete(key)
    except StorageError:
        log.warning("pdf not deleted for senior %s: %s", senior_id, key)
