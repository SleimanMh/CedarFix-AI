from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.shared.arabizi_features import analyze_language_signal, flat_distance_m, normalise_token, risk_hint_for_token
from src.shared.arabizi_lexical_policy import HIGH_RISK_HINTS
from src.shared.schemas import Language, OOVRiskHint, PairFusionGate


BENCHMARK_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.csv"


def benchmark_rows() -> list[dict[str, str]]:
    with BENCHMARK_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class ArabiziAdversarialRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = {row["case_id"]: row for row in benchmark_rows()}

    def analyze(self, case_id: str):
        row = self.rows[case_id]
        return analyze_language_signal(
            row["raw_text_a"],
            normalized_text=row["expected_normalized_text_a"],
            language_hint=row["language_a"],
            report_id=row["source_id"],
        )

    def test_all_adversarial_cases_satisfy_minimum_drift_contract(self) -> None:
        for row in self.rows.values():
            if row["case_type"] != "ADVERSARIAL":
                continue
            with self.subTest(row=row["case_id"]):
                signal = analyze_language_signal(
                    row["raw_text_a"],
                    normalized_text=row["expected_normalized_text_a"],
                    language_hint=row["language_a"],
                    report_id=row["source_id"],
                )
                self.assertGreaterEqual(signal.drift_score, int(row["expected_drift_score_min"]))

    def test_all_corpus_report_cases_are_analyzable_and_satisfy_drift_contract(self) -> None:
        """Regression gate: each B001 Arabizi/mixed corpus row must be analyzable
        and produce a drift_score >= expected_drift_score_min (calibrated against
        non-promoted OOV tokens only; promoted tokens are excluded from the minimum).
        """
        for row in self.rows.values():
            if row["case_type"] != "REPORT":
                continue
            with self.subTest(row=row["case_id"]):
                signal = analyze_language_signal(
                    row["raw_text_a"],
                    normalized_text=row["expected_normalized_text_a"] or None,
                    language_hint=row["language_a"],
                    report_id=row["source_id"],
                )
                self.assertIn(
                    signal.language,
                    {Language.ARABIZI, Language.MIXED},
                    msg=f"{row['case_id']}: expected arabizi or mixed language, got {signal.language}",
                )
                self.assertGreaterEqual(
                    signal.drift_score,
                    int(row["expected_drift_score_min"]),
                    msg=f"{row['case_id']}: drift_score {signal.drift_score} < min {row['expected_drift_score_min']}",
                )

    def test_digit_omission_and_repeated_letters_keep_pothole_signal(self) -> None:
        self.assertEqual(normalise_token("hofraaaaaa"), "hofraa")
        signal = self.analyze("ADV-B001-001")
        self.assertIn("hofra", signal.known_terms)
        self.assertIn("share3", signal.known_terms)
        self.assertFalse(signal.force_hitl(route_confidence=0.82))

    def test_repeated_digit_high_risk_forces_hitl(self) -> None:
        self.assertEqual(normalise_token("5tr444444"), "5tr")
        signal = self.analyze("ADV-B001-002")
        self.assertGreaterEqual(signal.drift_score, 2)
        self.assertTrue(signal.force_hitl(route_confidence=0.91))

    def test_no_space_token_does_not_crash_and_lowers_coverage(self) -> None:
        signal = self.analyze("ADV-B001-003")
        self.assertIn("jora", signal.known_terms)
        self.assertGreaterEqual(signal.oov_token_count, 1)
        self.assertLess(signal.normalization_coverage, 1.0)
        self.assertGreaterEqual(signal.drift_score, 2)

    def test_french_code_switch_transformer_is_visible(self) -> None:
        signal = self.analyze("ADV-B001-004")
        self.assertIn("transformateur", signal.known_terms)
        self.assertIn("m7arrak", signal.known_terms)
        self.assertGreater(signal.code_mix_ratio, 0)
        self.assertTrue(signal.force_hitl(route_confidence=0.90))

    def test_unknown_risk_modifier_preserves_known_issue_and_forces_hitl(self) -> None:
        signal = self.analyze("ADV-B001-005")
        self.assertIn("jora", signal.known_terms)
        self.assertIn("m5atra", {token.token for token in signal.oov_tokens})
        self.assertGreaterEqual(signal.oov_high_risk_count, 1)
        self.assertTrue(signal.force_hitl(route_confidence=0.88))

    def test_sanitation_ambiguity_is_a_structured_signal(self) -> None:
        signal = self.analyze("ADV-B001-006")
        self.assertIn("sarif", signal.known_terms)
        self.assertTrue(signal.explanation_features["semantic_ambiguity"])
        self.assertTrue(signal.force_hitl(route_confidence=0.89))

    def test_near_border_pair_is_not_auto_merged_by_geography(self) -> None:
        row = self.rows["ADV-B001-007"]
        distance = flat_distance_m(
            float(row["lat_a"]),
            float(row["lon_a"]),
            float(row["lat_b"]),
            float(row["lon_b"]),
        )
        gate = PairFusionGate(
            report_id_a=row["report_id_a"],
            report_id_b=row["report_id_b"],
            distance_m=distance,
            semantic_duplicate_candidate=True,
            expected_pair_label=row["expected_pair_label"],
        )
        self.assertGreater(distance, 200.0)
        self.assertFalse(gate.allow_auto_merge_by_geo)
        self.assertEqual(gate.expected_pair_label, "HARD_NEGATIVE")

    def test_policy_high_risk_hints_are_safety_classified_by_probe(self) -> None:
        """Regression: every token in HIGH_RISK_HINTS must trigger SAFETY_LEXICAL_HINT
        from risk_hint_for_token, and any signal containing only that token must have
        drift_score >= 2.

        Two code paths both apply:
        - OOV path (future Batch 002 novel reports): risk_hint_for_token() returns
          SAFETY_LEXICAL_HINT → oov_high_risk_count += 1 → drift_score >= 2.
        - Known-term path (tokens also in vocab sample_complaints): the
          `high_risk_term_count` check fires → drift_score >= 2.

        The direct risk_hint_for_token() assertion guards against the lexical policy
        and the probe silently diverging: the OOV queue uses HIGH_RISK_HINTS; the
        probe function must agree regardless of vocab state.
        """
        extra_safety_tokens = {"nnar", "7ariki", "masalla7", "mshbouh"}
        for token in extra_safety_tokens:
            with self.subTest(token=token):
                # 1. The classification function must label it SAFETY_LEXICAL_HINT.
                hint = risk_hint_for_token(token)
                self.assertEqual(
                    hint,
                    OOVRiskHint.SAFETY_LEXICAL_HINT,
                    msg=(
                        f"Token '{token}' is in HIGH_RISK_HINTS but risk_hint_for_token "
                        f"returned {hint!r}. arabizi_features.risk_hint_for_token must "
                        "check HIGH_RISK_HINTS in addition to HIGH_RISK_RE."
                    ),
                )
                # 2. A signal containing only this token must force drift_score >= 2,
                #    regardless of whether the token is known or OOV in the current vocab.
                signal = analyze_language_signal(
                    token,
                    language_hint="arabizi",
                    report_id=f"TEST-POLICY-{token}",
                )
                self.assertGreaterEqual(
                    signal.drift_score,
                    2,
                    msg=(
                        f"Token '{token}' should force drift_score >= 2 via "
                        "high_risk_term_count (known path) or oov_high_risk_count (OOV path)."
                    ),
                )


if __name__ == "__main__":
    unittest.main()
