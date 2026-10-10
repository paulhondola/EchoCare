"""Lifecycle of an incident: DAS's handling of one red (G16, 02 UC-11).

The values are what the `incident.status` column stores (05 §1). The incident records what
DAS did; it never changes the code (03 §8).
"""

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
