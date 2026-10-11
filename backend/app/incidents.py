"""Lifecycle of an incident: DAS's handling of one red (G16, 02 UC-11).

The values are what the `incident.status` column stores (05 §1). The incident records what
DAS did; it never changes the code (03 §8).
"""

import uuid
from enum import StrEnum

from app.calls import InvalidTransition
from app.status import Severity


class IncidentStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


# Taking an open incident, by "Preiau" or by answering the hand-over, makes it in_progress;
# resolving needs it taken first. Reopening is deferred past the MVP.
TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.open: frozenset({IncidentStatus.in_progress}),
    IncidentStatus.in_progress: frozenset({IncidentStatus.resolved}),
    IncidentStatus.resolved: frozenset(),
}

# At most one per senior, enforced by a partial unique index (05 §3).
UNRESOLVED = frozenset({IncidentStatus.open, IncidentStatus.in_progress})


def advance(current: IncidentStatus, new: IncidentStatus) -> IncidentStatus:
    """Move an incident on. Unlike a call, a repeat is refused: a second taker is told
    who has it instead of taking it again (05 §3).
    """
    if new not in TRANSITIONS[current]:
        raise InvalidTransition(f"incident cannot go from {current} to {new}")
    return new


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
    resolved_by: uuid.UUID | None,
    outcome: str | None,
    caller: uuid.UUID,
    wanted: str,
) -> str | None:
    """Why POST /incidents/{id}/resolve is refused, once its update changed nothing.

    An open incident is taken first (UC-11). Any DAS employee may resolve one in
    progress, so a shift change needs no hand-back. None for an exact repeat.
    """
    if status is IncidentStatus.open:
        return "wrong_state"
    if status is IncidentStatus.resolved and (
        resolved_by != caller or outcome != wanted
    ):
        return "already_done"
    return None
