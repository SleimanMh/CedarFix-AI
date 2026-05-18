from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.audit_cedarfix_next_phase_gates import audit as audit_next_phase  # noqa: E402
from scripts.audit_rubric_readiness import audit as audit_rubric  # noqa: E402


class CedarFixNextPhaseGateTests(unittest.TestCase):
    def test_next_phase_audit_prioritizes_iep2_first(self) -> None:
        result = audit_next_phase()
        self.assertEqual(result["summary"]["readiness"], "NOT_READY_FOR_FINAL_RELEASE")
        self.assertGreaterEqual(result["summary"]["gate_pass_count"], 1)
        self.assertEqual(result["recommended_build_order"][0]["rank"], 1)
        self.assertIn("IEP-2", result["recommended_build_order"][0]["task"])
        gate_ids = {gate["gate_id"] for gate in result["gates"]}
        self.assertEqual(
            gate_ids,
            {"CFX-G01", "CFX-G02", "CFX-G03", "CFX-G04", "CFX-G05", "CFX-G06", "CFX-G07", "CFX-G08", "CFX-G09"},
        )

    def test_rubric_audit_contains_all_weighted_items_and_blockers(self) -> None:
        result = audit_rubric()
        weighted_codes = {item["code"] for item in result["weighted_items"]}
        self.assertEqual(len(weighted_codes), 30)
        self.assertIn("T3", weighted_codes)
        self.assertIn("M3", weighted_codes)
        self.assertIn("IEP-2 dedup service and pair-eval artifact", result["summary"]["highest_roi_blockers"])
        self.assertLess(result["summary"]["weighted_item_average"], 1.0)


if __name__ == "__main__":
    unittest.main()
