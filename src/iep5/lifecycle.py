"""IEP-5 lifecycle orchestration helpers.

Pure decision helpers that sit on top of the guarded state machine in
``src.shared.lifecycle_schemas``.  Kept free of DB/Redis so they can be
unit-tested directly.
"""
from __future__ import annotations

from src.shared.lifecycle_schemas import (
    IncidentState,
    LifecycleEventType,
    is_reopen_trigger,
    next_state,
)

__all__ = ["plan_event_for_new_complaint", "PlannedTransition"]


class PlannedTransition:
    """Result of planning how a new complaint affects an incident."""

    __slots__ = ("event", "to_state", "is_reopen", "reason")

    def __init__(
        self,
        event: LifecycleEventType,
        to_state: IncidentState,
        is_reopen: bool,
        reason: str,
    ) -> None:
        self.event = event
        self.to_state = to_state
        self.is_reopen = is_reopen
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"PlannedTransition(event={self.event.value}, "
            f"to_state={self.to_state.value}, is_reopen={self.is_reopen})"
        )


def plan_event_for_new_complaint(current: IncidentState | None) -> PlannedTransition:
    """Decide the lifecycle event triggered by a freshly routed complaint.

    - No incident yet            → ROUTE into ROUTED.
    - Incident resolved/closed   → REOPEN (this is the retraining signal).
    - Incident already active    → ROUTE refresh (idempotent re-route).
    """
    if current is None:
        return PlannedTransition(
            event=LifecycleEventType.ROUTE,
            to_state=IncidentState.ROUTED,
            is_reopen=False,
            reason="new_incident",
        )

    if is_reopen_trigger(current):
        to_state = next_state(current, LifecycleEventType.REOPEN)
        return PlannedTransition(
            event=LifecycleEventType.REOPEN,
            to_state=to_state,
            is_reopen=True,
            reason=f"new_complaint_on_{current.value.lower()}_incident",
        )

    # Active incident — keep it where it is; record an attach as a re-route only
    # if a self ROUTE is legal, otherwise no state change.
    try:
        to_state = next_state(current, LifecycleEventType.ROUTE)
    except Exception:
        to_state = current
    return PlannedTransition(
        event=LifecycleEventType.ROUTE,
        to_state=to_state,
        is_reopen=False,
        reason="attach_to_active_incident",
    )
