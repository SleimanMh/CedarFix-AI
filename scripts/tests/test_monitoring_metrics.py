"""Prometheus metrics contract tests.

Verifies that all required ML-specific low-cardinality metric names are
documented in MONITORING_SIGNALS.md and follow CedarFix naming conventions.

Run with:
    python -m pytest scripts/tests/test_monitoring_metrics.py -v
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MONITORING_DOC = ROOT / "docs" / "MONITORING_SIGNALS.md"

# Required metric names that must be documented
REQUIRED_METRICS = [
    "cedarfix_complaints_received_total",
    "cedarfix_complaints_processed_total",
    "cedarfix_hitl_required_total",
    "cedarfix_routing_confidence",
    "cedarfix_iep1_drift_score",
    "cedarfix_iep2_duplicate_rate",
    "cedarfix_iep3_false_auto_route_total",
    "cedarfix_pipeline_latency_seconds",
    "cedarfix_oov_token_rate",
]

# High-cardinality labels that must NOT be used as Prometheus labels
FORBIDDEN_HIGH_CARDINALITY = [
    "complaint_id",
    "text_raw",
    "citizen_name",
]


class TestMonitoringSignalsDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MONITORING_DOC.exists():
            cls.doc_text = ""
        else:
            cls.doc_text = MONITORING_DOC.read_text(encoding="utf-8")

    def test_monitoring_doc_exists(self) -> None:
        self.assertTrue(MONITORING_DOC.exists(), "docs/MONITORING_SIGNALS.md must exist")

    def test_all_required_metrics_documented(self) -> None:
        for metric in REQUIRED_METRICS:
            with self.subTest(metric=metric):
                self.assertIn(
                    metric,
                    self.doc_text,
                    f"Required metric '{metric}' not found in MONITORING_SIGNALS.md",
                )

    def test_no_high_cardinality_labels(self) -> None:
        for label in FORBIDDEN_HIGH_CARDINALITY:
            with self.subTest(label=label):
                # Should not appear as a Prometheus label (in backtick or code block context)
                pattern = rf"`{re.escape(label)}`"
                if re.search(pattern, self.doc_text):
                    self.fail(
                        f"High-cardinality label '{label}' appears to be documented as a "
                        f"Prometheus label. Use only low-cardinality labels (sector, entity, state)."
                    )

    def test_sector_label_is_documented(self) -> None:
        self.assertIn("sector", self.doc_text.lower())

    def test_hitl_metric_is_documented(self) -> None:
        self.assertIn("hitl", self.doc_text.lower())

    def test_drift_metric_is_documented(self) -> None:
        self.assertIn("drift", self.doc_text.lower())

    def test_confidence_metric_is_documented(self) -> None:
        self.assertIn("confidence", self.doc_text.lower())

    def test_doc_has_prometheus_section(self) -> None:
        self.assertIn("Prometheus", self.doc_text)

    def test_doc_has_grafana_section(self) -> None:
        self.assertIn("Grafana", self.doc_text)

    def test_doc_has_alerting_section(self) -> None:
        self.assertTrue(
            "alert" in self.doc_text.lower() or "Alert" in self.doc_text,
            "MONITORING_SIGNALS.md should include an alerting section",
        )


if __name__ == "__main__":
    unittest.main()
