from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class NoExternalDataLayerTests(unittest.TestCase):
    def test_external_candidate_store_is_removed(self) -> None:
        forbidden_paths = [
            "data/external/arabizi_external_sources_manifest.csv",
            "data/external/external_arabizi_candidates_v1.csv",
            "data/external/external_arabizi_source_snapshot_v1.json",
        ]
        for relative in forbidden_paths:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())

    def test_external_pull_scripts_are_removed_from_current_plan(self) -> None:
        forbidden_paths = [
            "scripts/pull_external_arabizi_candidates.py",
            "scripts/validate_external_arabizi_candidates.py",
            "scripts/validate_external_arabizi_manifest.py",
            "docs/EXTERNAL_ARABIZI_CANDIDATE_PULL.md",
            "docs/EXTERNAL_ARABIZI_DATA_POLICY.md",
        ]
        for relative in forbidden_paths:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())


if __name__ == "__main__":
    unittest.main()
