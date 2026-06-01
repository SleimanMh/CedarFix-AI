"""CedarFix consolidated regression test suite.

Combines all tests from the previous individual test files:
  - test_arabizi_adversarial.py
  - test_arabizi_next_phase_gates.py
  - test_arabizi_reliability_certificate.py
  - test_arabizi_stress_lab.py
  - test_cedarfix_next_phase_gates.py
  - test_eep_iep1_contracts.py
  - test_no_external_data_layer.py

Run with:
  python -m pytest scripts/tests/test_suite.py -v
  python scripts/tests/test_suite.py
"""

from __future__ import annotations

import base64
import csv
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Imports from consolidated scripts
# ---------------------------------------------------------------------------
from scripts.audit import (  # noqa: E402
    audit_arabizi_gates,
    audit_next_phase_gates,
    audit_rubric,
)
from scripts.evaluate import (  # noqa: E402
    build_certificate,
    evaluate_pair_coverage,
    perturbations,
    render_html,
    run_stress_lab,
)
from src.eep.models import ComplaintRequest  # noqa: E402
from src.eep.pii import scrub_pii  # noqa: E402
from src.iep1.extractor import extract  # noqa: E402
from src.shared.arabizi_features import (  # noqa: E402
    analyze_language_signal,
    flat_distance_m,
    normalise_token,
    risk_hint_for_token,
)
from src.shared.arabizi_lexical_policy import HIGH_RISK_HINTS  # noqa: E402
from src.shared.schemas import Language, OOVRiskHint, PairFusionGate  # noqa: E402

BENCHMARK_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.csv"
# Human-authored corpus + its derived regression benchmark are LOCAL-ONLY
# artifacts (not committed; see docs/CEDARFIX_MASTER.md). On a fresh clone they
# are absent, so the tests that consume them skip cleanly instead of erroring.
CORPUS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
_HAS_BENCHMARK = BENCHMARK_PATH.exists()
_HAS_CORPUS = CORPUS_PATH.exists()


def benchmark_rows() -> list[dict[str, str]]:
    with BENCHMARK_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# ===========================================================================
# Arabizi adversarial regression tests
# ===========================================================================

class ArabiziAdversarialRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _HAS_BENCHMARK:
            raise unittest.SkipTest(
                f"local-only benchmark absent: {BENCHMARK_PATH.relative_to(ROOT)}"
            )
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
        extra_safety_tokens = {"nnar", "7ariki", "masalla7", "mshbouh"}
        for token in extra_safety_tokens:
            with self.subTest(token=token):
                hint = risk_hint_for_token(token)
                self.assertEqual(
                    hint,
                    OOVRiskHint.SAFETY_LEXICAL_HINT,
                    msg=(
                        f"Token '{token}' is in HIGH_RISK_HINTS but risk_hint_for_token "
                        f"returned {hint!r}."
                    ),
                )
                signal = analyze_language_signal(
                    token,
                    language_hint="arabizi",
                    report_id=f"TEST-POLICY-{token}",
                )
                self.assertGreaterEqual(signal.drift_score, 2)


# ===========================================================================
# Arabizi next-phase gate tests
# ===========================================================================

class ArabiziNextPhaseGateTests(unittest.TestCase):
    def test_excellence_audit_is_honest_about_not_final_ready_yet(self) -> None:
        if not _HAS_CORPUS:
            self.skipTest(f"local-only corpus absent: {CORPUS_PATH.relative_to(ROOT)}")
        result = audit_arabizi_gates()
        self.assertEqual(result["summary"]["readiness"], "NOT_READY_FOR_FINAL_ARABIZI_CLAIM")
        self.assertGreaterEqual(result["summary"]["gate_pass_count"], 1)
        gate_ids = {gate["gate_id"] for gate in result["gates"]}
        self.assertEqual(gate_ids, {"ARZ-G01", "ARZ-G02", "ARZ-G03", "ARZ-G04", "ARZ-G05", "ARZ-G06"})
        self.assertIn("Batch 002", result["next_actions_ranked"][0])

    def test_pair_coverage_reports_arabizi_involving_pairs(self) -> None:
        if not _HAS_CORPUS:
            self.skipTest(f"local-only corpus absent: {CORPUS_PATH.relative_to(ROOT)}")
        result = evaluate_pair_coverage()
        summary = result["summary"]
        self.assertGreater(summary["arabizi_pair_count"], 0)
        self.assertGreater(summary["cross_language_duplicate_count"], 0)
        self.assertIn("arabizi-en", result["language_pair_breakdown"])
        self.assertIn("ar-arabizi", result["language_pair_breakdown"])


# ===========================================================================
# Arabizi reliability certificate tests
# ===========================================================================

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


# ===========================================================================
# Arabizi stress lab tests
# ===========================================================================

class ArabiziStressLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_stress_lab()

    def test_stress_lab_has_demo_scale_and_coverage(self) -> None:
        self.assertGreaterEqual(self.result["meta"]["scenario_count"], 6)
        self.assertGreaterEqual(self.result["meta"]["variant_count"], 24)
        for scenario_id in (
            "STRESS-ROADS-POTHOLE",
            "STRESS-ELECTRICITY-TRANSFORMER",
            "STRESS-WATER-SEWAGE",
            "STRESS-SAFETY-FIRE",
            "STRESS-WASTE-COLLECTION",
            "STRESS-FLOODING-DRAIN",
        ):
            self.assertIn(scenario_id, self.result["scenario_summary"], msg=f"Missing {scenario_id}")

    def test_stress_lab_sector_coverage_is_complete(self) -> None:
        cov = self.result["sector_coverage"]
        self.assertIn("coverage_rate", cov)
        self.assertIn("exercised_sectors", cov)
        self.assertIn("missing_sectors", cov)
        self.assertEqual(cov["missing_sectors"], [], msg="Stress lab must cover all 6 canonical sectors")
        gates = self.result["acceptance_gates"]
        self.assertGreaterEqual(cov["coverage_rate"], gates["requires_sector_coverage_rate"])

    def test_stress_lab_meets_stability_gates(self) -> None:
        gates = self.result["acceptance_gates"]
        summary = self.result["summary"]
        self.assertGreaterEqual(summary["stable_sector_rate"], gates["min_stable_sector_rate"])
        self.assertGreaterEqual(summary["acceptable_decision_rate"], gates["min_acceptable_decision_rate"])
        self.assertGreaterEqual(summary["stable_issue_rate"], gates["min_strict_issue_rate_observed"])
        self.assertEqual(summary["unacceptable_count"], 0)

    def test_stress_lab_exercises_uncertainty_and_hitl(self) -> None:
        gates = self.result["acceptance_gates"]
        summary = self.result["summary"]
        hitl_count = round(summary["hitl_rate"] * self.result["meta"]["variant_count"])
        self.assertGreaterEqual(hitl_count, gates["requires_hitl_variant_count_at_least"])
        self.assertGreaterEqual(
            summary["oov_or_noise_variant_count"],
            gates["requires_oov_or_noise_variant_count_at_least"],
        )

    def test_each_variant_exposes_professor_visible_evidence(self) -> None:
        required_keys = {
            "variant_id",
            "raw_text",
            "predicted_sector",
            "predicted_issue_type",
            "issue_confidence",
            "acceptable_decision",
            "force_hitl",
            "drift_score",
            "normalization_coverage",
            "oov_tokens",
            "known_terms",
        }
        for row in self.result["variants"]:
            with self.subTest(variant=row["variant_id"]):
                self.assertTrue(required_keys <= row.keys())
                self.assertGreaterEqual(row["drift_score"], 0)
                self.assertLessEqual(row["drift_score"], 3)
                self.assertGreaterEqual(row["normalization_coverage"], 0.0)
                self.assertLessEqual(row["normalization_coverage"], 1.0)


# ===========================================================================
# CedarFix next-phase gate tests
# ===========================================================================

class CedarFixNextPhaseGateTests(unittest.TestCase):
    def test_next_phase_audit_prioritizes_iep2_first(self) -> None:
        result = audit_next_phase_gates()
        self.assertIn(result["summary"]["readiness"], {"NOT_READY_FOR_FINAL_RELEASE", "READY_FOR_FINAL_RELEASE"})
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


# ===========================================================================
# EEP + IEP-1 contract tests
# ===========================================================================

class EEPRequestContractTests(unittest.TestCase):
    def test_language_hint_is_normalized_and_limited(self) -> None:
        payload = ComplaintRequest(
            text="fi jora kbire 3al tari2",
            gps_lat=33.8897,
            gps_lon=35.48,
            language_hint="ARABIZI",
        )
        self.assertEqual(payload.language_hint, "arabizi")

        with self.assertRaises(ValidationError):
            ComplaintRequest(text="fi jora kbire", language_hint="spanish")

    def test_gps_must_be_pair_and_inside_lebanon(self) -> None:
        with self.assertRaises(ValidationError):
            ComplaintRequest(text="fi jora kbire 3al tari2", gps_lat=33.8897)

        with self.assertRaises(ValidationError):
            ComplaintRequest(
                text="fi jora kbire 3al tari2",
                gps_lat=48.8566,
                gps_lon=2.3522,
            )

    def test_image_must_be_real_jpeg_or_png_base64(self) -> None:
        tiny_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8).decode()
        payload = ComplaintRequest(text="broken drain in Hamra", image_b64=tiny_png)
        self.assertEqual(payload.image_b64, tiny_png)

        with self.assertRaises(ValidationError):
            ComplaintRequest(text="broken drain in Hamra", image_b64="not-base64")

        fake_payload = base64.b64encode(b"GIF89a").decode()
        with self.assertRaises(ValidationError):
            ComplaintRequest(text="broken drain in Hamra", image_b64=fake_payload)

    def test_pii_scrubber_removes_phone_and_email(self) -> None:
        scrubbed = scrub_pii("Call me on +961 3 123 456 or user@example.com about this")
        self.assertNotIn("+961", scrubbed)
        self.assertNotIn("user@example.com", scrubbed)
        self.assertIn("[PHONE]", scrubbed)
        self.assertIn("[EMAIL]", scrubbed)


class IEP1ExtractionContractTests(unittest.TestCase):
    def test_pothole_with_high_risk_modifier_preserves_specific_issue(self) -> None:
        result = extract("demo-1", "fi jora kbire 3al tari2 w l wad3 m5atra ktir", "arabizi", include_embedding=False)
        self.assertEqual(result["routing_sector"], "ROADS")
        self.assertEqual(result["issue_type"], "POTHOLE")
        self.assertGreaterEqual(result["drift_score"], 2)

    def test_transformer_code_switch_routes_to_transformer_fault(self) -> None:
        result = extract(
            "demo-2",
            "transformateur m7arrak bi borj 7ammoud w fi ri7et 7ar2",
            "mixed",
            include_embedding=False,
        )
        self.assertEqual(result["routing_sector"], "ELECTRICITY")
        self.assertEqual(result["issue_type"], "TRANSFORMER_FAULT")
        self.assertGreaterEqual(result["drift_score"], 2)

    def test_sewage_ambiguity_preserves_water_issue(self) -> None:
        result = extract("demo-3", "may ws5a w ri7et sarif 3al tari2 bi bliss", "arabizi", include_embedding=False)
        self.assertEqual(result["routing_sector"], "WATER")
        self.assertEqual(result["issue_type"], "SEWAGE_OVERFLOW")
        self.assertGreaterEqual(result["drift_score"], 2)


# ===========================================================================
# No-external-data-layer contract tests
# ===========================================================================

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
