"""Writing the senior's code and its reports. Deciding them is the caller's: the call's
ending step and the status engine (03 §6, §8). Nothing here commits (ADR-005)."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.codes.models import ReportSource, SeniorStatus, StatusReport
from app.core.changes import Change, ChangeKind, note
from app.status.engine import Certainty, Severity


async def set_code(
    session: AsyncSession,
    senior_id: uuid.UUID,
    call_id: uuid.UUID,
    code: Severity,
    reason: str,
    since: datetime,
) -> None:
    """The senior's current code, a new row or the old one replaced (05 §2). Noted for
    the pushes with the code it replaced (04 §6)."""
    before = await session.scalar(
        select(SeniorStatus.code).where(SeniorStatus.senior_id == senior_id)
    )
    row = {"code": code, "reason": reason, "since": since, "source_call_id": call_id}
    await session.execute(
        insert(SeniorStatus)
        .values(senior_id=senior_id, **row)
        .on_conflict_do_update(index_elements=[SeniorStatus.senior_id], set_=row)
    )
    note(
        session,
        Change(
            ChangeKind.code,
            senior_id,
            # An unknown name, from a newer copy, reads back as the bare string (05 §2)
            before=getattr(before, "name", before),
            after=code.name,
        ),
    )


def add_report(
    session: AsyncSession,
    call_id: uuid.UUID,
    source: ReportSource,
    severity: Severity,
    reason: str,
    *,
    certainty: Certainty | None = None,
) -> None:
    """One severity a call reached, for the audit trail behind a code (05 §2)."""
    session.add(
        StatusReport(
            call_id=call_id,
            source=source,
            severity=severity,
            certainty=certainty,
            reason=reason,
        )
    )


async def erase_senior_codes(
    session: AsyncSession, senior_id: uuid.UUID, call_ids: list[uuid.UUID]
) -> None:
    """The senior's status reports and current code, for an erasure (design
    2026-11-14). Doesn't commit (ADR-005)."""
    await session.execute(
        delete(StatusReport).where(StatusReport.call_id.in_(call_ids))
    )
    await session.execute(
        delete(SeniorStatus).where(SeniorStatus.senior_id == senior_id)
    )
