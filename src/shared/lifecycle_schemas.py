"""IEP-5 incident lifecycle contracts.

The lifecycle service turns a stream of routed complaints into an
event-sourced incident state machine.  Every state transition is an
append-only event; ``REOPENED`` transitions are the project's
"retraining signal" novel element — when a previously resolved incident
receives a new matching complaint, the original routing decision is
captured as a retraining candidate.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "IncidentState",
    "LifecycleEventType",
    "ALLOWED_TRANSITIONS",
    "REOPEN_TRIGGER_STATES",
    "InvalidTransition",
    "next_state",
    "is_reopen_trigger",
    "is_terminal",
    "LifecycleTransition",
    "RetrainingCandidatePacket",
]


class IncidentState(str, Enum):
    OPEN = "OPEN"
    ROUTED = "ROUTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    CLOSED = "CLOSED"


class LifecycleEventType(str, Enum):
    OPEN = "open"
    ROUTE = "route"
    ACKNOWLEDGE = "acknowledge"
    START = "start"
    RESOLVE = "resolve"
    REOPEN = "reopen"
    CLOSE = "close"


# Event → resulting state.
_EVENT_TARGET: dict[LifecycleEventType, IncidentState] = {
    LifecycleEventType.OPEN: IncidentState.OPEN,
    LifecycleEventType.ROUTE: IncidentState.ROUTED,
    LifecycleEventType.ACKNOWLEDGE: IncidentState.ACKNOWLEDGED,
    LifecycleEventType.START: IncidentState.IN_PROGRESS,
    LifecycleEventType.RESOLVE: IncidentState.RESOLVED,
    LifecycleEventType.REOPEN: IncidentState.REOPENED,
    LifecycleEventType.CLOSE: IncidentState.CLOSED,
}

# Guarded transition table — illegal transitions raise InvalidTransition.
ALLOWED_TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.OPEN: {IncidentState.ROUTED, IncidentState.CLOSED},
    IncidentState.ROUTED: {
        IncidentState.ACKNOWLEDGED,
        IncidentState.IN_PROGRESS,
        IncidentState.RESOLVED,
        IncidentState.CLOSED,
    },
    IncidentState.ACKNOWLEDGED: {
        IncidentState.IN_PROGRESS,
        IncidentState.RESOLVED,
        IncidentState.CLOSED,
    },
    IncidentState.IN_PROGRESS: {IncidentState.RESOLVED, IncidentState.CLOSED},
    IncidentState.RESOLVED: {IncidentState.REOPENED, IncidentState.CLOSED},
    IncidentState.REOPENED: {
        IncidentState.ACKNOWLEDGED,
        IncidentState.IN_PROGRESS,
        IncidentState.RESOLVED,
        IncidentState.CLOSED,
    },
    IncidentState.CLOSED: {IncidentState.REOPENED},
}

# A new complaint attaching to an incident in one of these states means the
# work was thought finished but the problem recurred — a reopen.
REOPEN_TRIGGER_STATES: frozenset[IncidentState] = frozenset(
    {IncidentState.RESOLVED, IncidentState.CLOSED}
)


class InvalidTransition(ValueError):
    """Raised when an event would move an incident through a forbidden edge."""


def next_state(current: IncidentState, event: LifecycleEventType) -> IncidentState:
    """Return the state produced by applying ``event`` to ``current``.

    Raises:
        InvalidTransition: if the edge is not in ``ALLOWED_TRANSITIONS``.
    """
    target = _EVENT_TARGET[event]
    if target == current:
        # Idempotent self-transition is allowed (e.g. re-route refresh) only
        # when the state legitimately permits looping back to itself.
        if target in ALLOWED_TRANSITIONS.get(current, set()):
            return target
        raise InvalidTransition(f"{current.value} -> {target.value} not allowed")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(
            f"illegal transition {current.value} --{event.value}--> {target.value}"
        )
    return target


def is_reopen_trigger(current: IncidentState) -> bool:
    """True if a fresh matching complaint should reopen ``current``."""
    return current in REOPEN_TRIGGER_STATES


def is_terminal(state: IncidentState) -> bool:
    """CLOSED is the only quasi-terminal state (still reopenable)."""
    return state == IncidentState.CLOSED


class LifecycleTransition(BaseModel):
    """One append-only lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(..., min_length=1)
    complaint_id: str | None = None
    from_state: IncidentState | None = None
    to_state: IncidentState
    event: LifecycleEventType
    reason: str = Field(default="", max_length=256)
    actor: str = Field(default="system", min_length=1, max_length=64)


class RetrainingCandidatePacket(BaseModel):
    """Snapshot captured when an incident reopens or drift is detected."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    incident_id: str | None = None
    source: str = Field(..., min_length=1)  # reopen | drift | oov
    reason: str = Field(default="", max_length=256)
    original_routing: dict = Field(default_factory=dict)
    retraining_priority_score: float = Field(default=0.0, ge=0.0, le=1.0)
    retraining_priority_reasons: list[str] = Field(default_factory=list)
