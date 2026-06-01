"""Tests for the shared Prometheus metrics surface.

Guards the credibility of the observability story: every service that
``infra/prometheus.yml`` scrapes must actually expose a ``/metrics`` endpoint,
and the metric names must match ``docs/MONITORING_SIGNALS.md``.
"""
from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.shared import metrics as M


class TestMetricsModule(unittest.TestCase):
    def test_prometheus_client_available(self) -> None:
        # The repo pins prometheus-client; if this fails the dep is missing.
        self.assertTrue(M.PROMETHEUS_AVAILABLE)

    def test_documented_core_metrics_exist(self) -> None:
        for attr in (
            "COMPLAINTS_RECEIVED",
            "COMPLAINTS_PROCESSED",
            "HITL_REQUIRED",
            "PIPELINE_LATENCY",
            "IEP1_DRIFT_SCORE",
            "OOV_TOKEN_RATE",
            "ROUTING_CONFIDENCE",
            "IEP3_PRIORITY_SCORE",
            "IEP5_REOPEN_TOTAL",
            "IEP6_FUSION_TOTAL",
            "IEP6_IMAGE_CONFIDENCE",
        ):
            self.assertTrue(hasattr(M, attr), f"missing metric {attr}")


class TestMetricsEndpoints(unittest.TestCase):
    def test_all_scraped_services_expose_metrics(self) -> None:
        # Drive at least one observation so the exposition is non-empty.
        M.COMPLAINTS_RECEIVED.labels(source="test").inc()
        M.ROUTING_CONFIDENCE.labels(sector="WATER").observe(0.8)
        M.IEP6_FUSION_TOTAL.labels(decision="agree").inc()

        import src.eep.main as eep_main
        import src.iep1.main as iep1_main
        import src.iep2.main as iep2_main
        import src.iep3.main as iep3_main
        import src.iep4.main as iep4_main
        import src.iep5.main as iep5_main
        import src.iep6.main as iep6_main

        for mod, name in (
            (eep_main, "eep"),
            (iep1_main, "iep1"),
            (iep2_main, "iep2"),
            (iep3_main, "iep3"),
            (iep4_main, "iep4"),
            (iep5_main, "iep5"),
            (iep6_main, "iep6"),
        ):
            with self.subTest(service=name):
                client = TestClient(mod.app)
                resp = client.get("/metrics")
                self.assertEqual(resp.status_code, 200)
                self.assertIn("cedarfix_", resp.text)


if __name__ == "__main__":
    unittest.main()
