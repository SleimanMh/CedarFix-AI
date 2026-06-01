"""IEP-6 image/text late-fusion tests (pure, no torch required).

Run with:
    python -m pytest scripts/tests/test_iep6_image_fusion.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.shared.image_schemas import (  # noqa: E402
    AGREE_BOOST,
    CONFLICT_PENALTY,
    IMAGE_LABEL_TO_SECTOR,
    MIN_IMAGE_CONFIDENCE,
    fuse_image_text,
)


class TestFusion(unittest.TestCase):
    def test_no_image_signal_when_absent(self) -> None:
        decision = fuse_image_text("ROADS", None, None)
        self.assertEqual(decision.agreement, "no_image_signal")
        self.assertEqual(decision.confidence_delta, 0.0)
        self.assertFalse(decision.force_hitl)

    def test_low_confidence_image_is_ignored(self) -> None:
        decision = fuse_image_text("ROADS", "ROADS", MIN_IMAGE_CONFIDENCE - 0.05)
        self.assertEqual(decision.agreement, "no_image_signal")

    def test_agreement_boosts_confidence(self) -> None:
        decision = fuse_image_text("ROADS", "ROADS", 0.9)
        self.assertEqual(decision.agreement, "agree")
        self.assertAlmostEqual(decision.confidence_delta, AGREE_BOOST)
        self.assertFalse(decision.force_hitl)

    def test_conflict_penalises_and_forces_hitl(self) -> None:
        decision = fuse_image_text("ROADS", "WATER", 0.9)
        self.assertEqual(decision.agreement, "conflict")
        self.assertAlmostEqual(decision.confidence_delta, -CONFLICT_PENALTY)
        self.assertTrue(decision.force_hitl)

    def test_uncertain_text_lets_image_disambiguate(self) -> None:
        decision = fuse_image_text("OTHER", "WATER", 0.9)
        self.assertEqual(decision.agreement, "image_disambiguates")
        self.assertFalse(decision.force_hitl)
        self.assertGreater(decision.confidence_delta, 0.0)

    def test_taxonomy_maps_to_known_sectors(self) -> None:
        sectors = {sector for _label, sector in IMAGE_LABEL_TO_SECTOR.values()}
        # "none" maps to None; the rest must be real sectors.
        self.assertIn(None, sectors)
        self.assertIn("ROADS", sectors)
        self.assertIn("WATER", sectors)
        self.assertIn("ELECTRICITY", sectors)


if __name__ == "__main__":
    unittest.main()
