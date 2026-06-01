"""IEP-6 multimodal late-fusion benchmark.

Turns "we added CLIP" into *measured* evidence. The benchmark exercises the
late-fusion decision logic (``fuse_image_text``) over a labelled fixture that
covers every hazard sector and all four decision branches (agree / conflict /
image_disambiguates / no_image_signal). It is deterministic and requires no
model weights, so it runs in CI.

Fixture: ``data/eval/image_hazard_fusion_eval_v1.jsonl``.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.shared.image_schemas import IMAGE_LABEL_TO_SECTOR, fuse_image_text

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "eval"
    / "image_hazard_fusion_eval_v1.jsonl"
)


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    with _FIXTURE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _delta_sign(delta: float) -> str:
    if delta > 1e-9:
        return "positive"
    if delta < -1e-9:
        return "negative"
    return "zero"


class TestImageFusionBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_cases()

    def test_fixture_is_non_trivial(self) -> None:
        self.assertGreaterEqual(len(self.cases), 12)

    def test_every_hazard_sector_is_covered(self) -> None:
        covered = {
            c["image_sector"]
            for c in self.cases
            if c["image_sector"] is not None
        }
        expected = {
            sector
            for _, sector in IMAGE_LABEL_TO_SECTOR.values()
            if sector is not None
        }
        missing = expected - covered
        self.assertEqual(missing, set(), f"hazard sectors not benchmarked: {missing}")

    def test_all_decision_branches_present(self) -> None:
        branches = {c["expected_agreement"] for c in self.cases}
        self.assertSetEqual(
            branches,
            {"agree", "conflict", "image_disambiguates", "no_image_signal"},
        )

    def test_fusion_matches_expectations(self) -> None:
        correct = 0
        for case in self.cases:
            with self.subTest(case=case["id"]):
                decision = fuse_image_text(
                    text_sector=case["text_sector"],
                    image_sector=case["image_sector"],
                    image_confidence=case["image_confidence"],
                )
                self.assertEqual(decision.agreement, case["expected_agreement"])
                self.assertEqual(decision.force_hitl, case["expected_force_hitl"])
                self.assertEqual(
                    _delta_sign(decision.confidence_delta),
                    case["expected_delta_sign"],
                )
                correct += 1
        # The fusion contract is deterministic — accuracy must be perfect.
        self.assertEqual(correct, len(self.cases))

    def test_conflicts_always_force_hitl(self) -> None:
        # Safety invariant: an image/text conflict must never auto-route.
        for case in self.cases:
            if case["expected_agreement"] == "conflict":
                decision = fuse_image_text(
                    text_sector=case["text_sector"],
                    image_sector=case["image_sector"],
                    image_confidence=case["image_confidence"],
                )
                self.assertTrue(decision.force_hitl, case["id"])


if __name__ == "__main__":
    unittest.main()
