"""Exporting a senior and everything stored about them (GDPR Art. 15 & 20; 04 §1).

Each table's owner reads its own rows (ADR-005); this module assembles them into a
single machine-readable JSON document.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller
from app.codes.service import export_senior_codes
from app.core.storage import StorageService
from app.export.schemas import (
    ExportAnswer,
    ExportCall,
    ExportConsent,
    ExportEvent,
    ExportIncident,
    ExportReport,
    ExportStatus,
    ExportSummary,
    ExportTurn,
    ExportWatch,
    ExportWatchReading,
    SeniorExport,
)
from app.incidents.service import export_senior_incidents
from app.medical.service import export_record
from app.seniors.schemas import WatchView
from app.seniors.service import editable_senior, export_senior_children, senior_view
from app.voice.service import export_calls

log = logging.getLogger("echocare.export")

CALL_FIELDS = ExportCall.model_fields.keys() - {"turns", "answers", "reports"}


async def export_senior(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    storage: StorageService,
) -> SeniorExport:
    """Reads the senior and every row about them across owners, applying need-to-know
    rules on unconfirmed medical records (01 §6, design 2026-11-14)."""
    senior = await editable_senior(session, caller, senior_id)
    is_medic = Role.medic in caller.roles and senior.medic_id == caller.user.id

    view = await senior_view(session, senior)
    consents, summaries, watch_state, watch_readings = await export_senior_children(
        session, senior_id
    )
    events, incidents = await export_senior_incidents(session, senior_id)
    calls, turns, answers = await export_calls(session, senior_id)
    status, reports = await export_senior_codes(
        session, senior_id, [c.id for c in calls]
    )
    medical = await export_record(session, senior_id, storage, full=is_medic)

    exported = SeniorExport(
        exported_at=datetime.now(UTC),
        senior=view,
        status=ExportStatus.model_validate(status, from_attributes=True)
        if status
        else None,
        consents=[
            ExportConsent.model_validate(c, from_attributes=True) for c in consents
        ],
        summaries=[
            ExportSummary.model_validate(s, from_attributes=True) for s in summaries
        ],
        medical_record=medical,
        watch=ExportWatch(
            state=WatchView.model_validate(watch_state, from_attributes=True)
            if watch_state
            else None,
            readings=[
                ExportWatchReading.model_validate(r, from_attributes=True)
                for r in watch_readings
            ],
        ),
        events=[ExportEvent.model_validate(e, from_attributes=True) for e in events],
        incidents=[
            ExportIncident.model_validate(i, from_attributes=True) for i in incidents
        ],
        calls=[
            ExportCall(
                **{name: getattr(c, name) for name in CALL_FIELDS},
                turns=[
                    ExportTurn.model_validate(t, from_attributes=True)
                    for t in turns[c.id]
                ],
                answers=[
                    ExportAnswer.model_validate(a, from_attributes=True)
                    for a in answers[c.id]
                ],
                reports=[
                    ExportReport.model_validate(r, from_attributes=True)
                    for r in reports[c.id]
                ],
            )
            for c in calls
        ],
    )
    log.info("exported senior %s by user %s", senior_id, caller.user.id)
    return exported
