import uuid

from app.incidents.models import IncidentStatus
from app.status.engine import Severity


def opens_incident(result: Severity, unresolved: bool) -> bool:
    """Whether a call's result opens a new incident (G16).

    A later red while one is open or in progress is added to that one, through the call.
    """
    return result is Severity.red and not unresolved


def take_refusal(
    status: IncidentStatus, taken_by: uuid.UUID | None, caller: uuid.UUID
) -> str | None:
    """Why POST /incidents/{id}/take is refused, once its update changed nothing (04 §2).

    None for the person who already has it: a repeated command has no second effect
    (04 §0). Anyone else is told who has it.
    """
    if status is IncidentStatus.resolved:
        return "wrong_state"
    if status is IncidentStatus.in_progress and taken_by != caller:
        return "already_done"
    return None


def resolve_refusal(
    status: IncidentStatus,
    done: tuple[uuid.UUID | None, str | None, str | None],
    wanted: tuple[uuid.UUID, str, str],
) -> str | None:
    """Why POST /incidents/{id}/resolve is refused, once its update changed nothing.

    An open incident is taken first (UC-11). Any DAS employee may resolve one in
    progress, so a shift change needs no hand-back. `done` and `wanted` are who, the
    outcome and the note; None only for an exact repeat (04 §2).
    """
    if status is IncidentStatus.open:
        return "wrong_state"
    if status is IncidentStatus.resolved and done != wanted:
        return "already_done"
    return None
