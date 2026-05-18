from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.certify_arabizi_input import build_certificate, perturbations, render_html  # noqa: E402


class ArabiziReliabilityCertificateTests(unittest.TestCase):
    def test_perturbations_are_live_and_adversarial(self) -> None:
        variants = perturbations("fi jora kbire 3al tari2 w l wad3 m5atra ktir")
        perturbation_names = {item["perturbation"] for item in variants}
        self.assertGreaterEqual(len(variants), 6)
        self.assertIn("original input", perturbation_names)
        self.assertIn("panic shorthand prefix", perturbation_names)
        self.assertIn("mobile no-space fusion", perturbation_names)
        self.assertIn("French/English code switch", perturbation_names)

    def test_default_certificate_is_stable_and_reviewable(self) -> None:
        cert = build_certificate("fi jora kbire 3al tari2 w l wad3 m5atra ktir", "arabizi")
        summary = cert["summary"]
        self.assertEqual(cert["original_decision"]["routing_sector"], "ROADS")
        self.assertEqual(cert["original_decision"]["issue_type"], "POTHOLE")
        self.assertGreaterEqual(summary["stable_sector_rate"], 0.9)
        self.assertGreaterEqual(summary["stable_issue_rate"], 0.85)
        self.assertEqual(summary["reliability_grade"], "A")
        self.assertIn("m5atra", summary["unique_oov_tokens"])
        self.assertGreaterEqual(summary["hitl_rate"], 0.5)

    def test_certificate_html_contains_professor_visible_evidence(self) -> None:
        cert = build_certificate("transformateur m7arrak bi borj 7ammoud w fi ri7et 7ar2", "mixed")
        page = render_html(cert)
        self.assertIn("CedarFix Arabizi Reliability Certificate", page)
        self.assertIn("Original Decision", page)
        self.assertIn("Variant Evidence", page)
        self.assertIn("Stable Sector", page)
        self.assertIn("HITL Rate", page)


if __name__ == "__main__":
    unittest.main()
