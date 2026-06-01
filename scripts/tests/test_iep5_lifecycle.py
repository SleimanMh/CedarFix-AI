"""IEP-5 lifecycle state-machine tests.

Validates the guarded transition table, reopen detection and the
new-complaint planning helper — all pure logic, no DB/Redis.

Run with:
    python -m pytest scripts/tests/test_iep5_lifecycle.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep5.lifecycle import plan_event_for_new_complaint  # noqa: E402
from src.shared.lifecycle_schemas import (  # noqa: E402
    IncidentState,
    InvalidTransition,
    LifecycleEventType,
    is_reopen_trigger,
    is_terminal,
    next_state,
)


class TestTransitions(unittest.TestCase):
    def test_legal_happy_path(self) -> None:
        state = IncidentState.OPEN
        for event, expected in [
            (LifecycleEventType.ROUTE, IncidentState.ROUTED),
            (LifecycleEventType.ACKNOWLEDGE, IncidentState.ACKNOWLEDGED),
            (LifecycleEventType.START, IncidentState.IN_PROGRESS),
            (LifecycleEventType.RESOLVE, IncidentState.RESOLVED),
            (LifecycleEventType.CLOSE, IncidentState.CLOSED),
        ]:
            state = next_state(state, event)
            self.assertEqual(state, expected)

    def test_illegal_transition_raises(self) -> None:
        # Cannot resolve straight from OPEN.
        with self.assertRaises(InvalidTransition):
            next_state(IncidentState.OPEN, LifecycleEventType.RESOLVE)

    def test_reopen_from_resolved_and_closed(self) -> None:
        self.assertEqual(
            next_state(IncidentState.RESOLVED, LifecycleEventType.REOPEN),
            IncidentState.REOPENED,
        )
        self.assertEqual(
            next_state(IncidentState.CLOSED, LifecycleEventType.REOPEN),
            IncidentState.REOPENED,
        )

    def test_reopen_trigger_states(self) -> None:
        self.assertTrue(is_reopen_trigger(IncidentState.RESOLVED))
        self.assertTrue(is_reopen_trigger(IncidentState.CLOSED))
        self.assertFalse(is_reopen_trigger(IncidentState.IN_PROGRESS))

    def test_terminal(self) -> None:
        self.assertTrue(is_terminal(IncidentState.CLOSED))
        self.assertFalse(is_terminal(IncidentState.RESOLVED))


class TestPlanning(unittest.TestCase):
    def test_new_incident_routes(self) -> None:
        plan = plan_event_for_new_complaint(None)
        self.assertEqual(plan.event, LifecycleEventType.ROUTE)
        self.assertEqual(plan.to_state, IncidentState.ROUTED)
        self.assertFalse(plan.is_reopen)

    def test_resolved_incident_reopens(self) -> None:
        plan = plan_event_for_new_complaint(IncidentState.RESOLVED)
        self.assertTrue(plan.is_reopen)
        self.assertEqual(plan.to_state, IncidentState.REOPENED)

    def test_closed_incident_reopens(self) -> None:
        plan = plan_event_for_new_complaint(IncidentState.CLOSED)
        self.assertTrue(plan.is_reopen)

    def test_active_incident_does_not_reopen(self) -> None:
        plan = plan_event_for_new_complaint(IncidentState.IN_PROGRESS)
        self.assertFalse(plan.is_reopen)


if __name__ == "__main__":
    unittest.main()
