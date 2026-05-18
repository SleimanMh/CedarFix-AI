#!/usr/bin/env python3
"""C-phase offline evaluation harness for the IEP-1 Arabizi heuristic probe.

Reads all Arabizi/mixed rows from the Batch 001 corpus and reports:

  1. Per-sector known-term coverage and drift distribution
  2. Issue-type recall: probe (with normalization) vs. B1 raw (exact token, no
     normalization) baseline — measures the concrete gain from normalization
  3. HITL drift-trigger rates at the operative confidence threshold
  4. Per-row diagnostic table

Outputs
-------
  Console:   formatted summary table
  JSON:      data/eval/arabizi_coverage_batch001.json
             (re-running overwrites with fresh values and timestamp)

Usage
-----
  python scripts/evaluate_arabizi_coverage.py            # full report + JSON
  python scripts/evaluate_arabizi_coverage.py --json     # JSON to stdout only
  python scripts/evaluate_arabizi_coverage.py --no-save  # skip JSON write

Notes
-----
- "Probe recall" = known_terms contains ≥1 token whose token_issue_map entry
  includes the correct issue_type.  Uses vocab-normalised token lookup.
- "B1 raw recall" = any raw lowercase token from raw_text is directly present
  as a key in token_issue_map for the correct issue_type.  No normalise_token.
  Difference reveals how much normalisation (strip trailing Arabic numeral
  proxies, hard-collapse repeats, embedded match) adds over exact lookup.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.shared.arabizi_features import (  # noqa: E402
    TOKEN_RE,
    VocabularyIndex,
    analyze_language_signal,
    load_vocabulary_index,
)
from src.shared.schemas import ROUTE_CONFIDENCE_THRESHOLD  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
OUTPUT_PATH = ROOT / "data" / "eval" / "arabizi_coverage_batch001.json"

ARABIZI_LANGUAGES: frozenset[str] = frozenset({"arabizi", "mixed"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def issue_type_hit_probe(
    known_terms: list[str],
    expected_issue: str,
    vocab: VocabularyIndex,
) -> bool:
    """True if any known_term resolves to expected_issue via token_issue_map.

    Uses the probe's already-normalised known_terms list.  Because
    token_issue_map keys are built with normalise_token(), this is a direct
    dict lookup — no further normalisation needed.
    """
    target = expected_issue.upper()
    for term in known_terms:
        for _sector, issue in vocab.token_issue_map.get(term, set()):
            if issue == target:
                return True
    return False


def issue_type_hit_b1_raw(
    raw_text: str,
    expected_issue: str,
    vocab: VocabularyIndex,
) -> bool:
    """B1 baseline: exact lowercase token lookup, zero normalization.

    Tokenises raw_text with TOKEN_RE and lower-cases each token, then checks
    whether any token appears verbatim as a key in token_issue_map for the
    expected issue_type.  This represents a naive "direct dictionary lookup"
    without the probe's normalise_token / token_variants pipeline.
    """
    target = expected_issue.upper()
    for match in TOKEN_RE.finditer(raw_text):
        token = match.group(0).lower()
        for _sector, issue in vocab.token_issue_map.get(token, set()):
            if issue == target:
                return True
    return False


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate(reports_path: Path = REPORTS_PATH) -> dict[str, Any]:
    vocab = load_vocabulary_index()
    rows = read_csv(reports_path)
    arabizi_rows = [r for r in rows if r["language"] in ARABIZI_LANGUAGES]

    per_row: list[dict[str, Any]] = []
    sector_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "coverage_sum": 0.0,
            "drift_scores": [0, 0, 0, 0],
            "oov_sum": 0,
            "hitl_ground_truth": 0,
            "hitl_drift_triggered": 0,
            "recall_probe": 0,
            "recall_b1": 0,
        }
    )

    drift_dist = [0, 0, 0, 0]
    total_coverage = 0.0
    total_oov = 0
    total_hitl_labeled = 0
    total_hitl_drift = 0
    drift_hitl_tp = 0
    drift_hitl_fp = 0
    drift_hitl_fn = 0
    total_recall_probe = 0
    total_recall_b1 = 0
    orthographic_noise_rows = 0
    semantic_ambiguity_rows = 0

    for row in arabizi_rows:
        report_id = row["report_id"]
        raw_text = row["raw_text"]
        normalized_text = row["normalized_text"]
        language_hint = row["language"]
        expected_issue = row["issue_type"]
        sector = row["sector"]
        hitl_labeled = row["hitl_required"].lower() == "true"

        signal = analyze_language_signal(
            raw_text,
            normalized_text=normalized_text,
            language_hint=language_hint,
            report_id=report_id,
        )

        recall_probe = issue_type_hit_probe(signal.known_terms, expected_issue, vocab)
        recall_b1 = issue_type_hit_b1_raw(raw_text, expected_issue, vocab)
        hitl_drift = signal.drift_score >= 2
        orthographic_noise_count = int(signal.explanation_features.get("orthographic_noise_count", 0))
        semantic_ambiguity = bool(signal.explanation_features.get("semantic_ambiguity", False))

        per_row.append(
            {
                "report_id": report_id,
                "language": language_hint,
                "sector": sector,
                "issue_type": expected_issue,
                "coverage": signal.normalization_coverage,
                "oov_token_count": signal.oov_token_count,
                "oov_tokens": [t.token for t in signal.oov_tokens],
                "drift_score": signal.drift_score,
                "known_terms": signal.known_terms,
                "orthographic_noise_count": orthographic_noise_count,
                "semantic_ambiguity": semantic_ambiguity,
                "hitl_labeled": hitl_labeled,
                "hitl_drift_triggered": hitl_drift,
                "recall_probe": recall_probe,
                "recall_b1_raw": recall_b1,
            }
        )

        drift_dist[signal.drift_score] += 1
        total_coverage += signal.normalization_coverage
        total_oov += signal.oov_token_count
        if hitl_labeled:
            total_hitl_labeled += 1
        if hitl_drift:
            total_hitl_drift += 1
        if hitl_labeled and hitl_drift:
            drift_hitl_tp += 1
        elif hitl_drift and not hitl_labeled:
            drift_hitl_fp += 1
        elif hitl_labeled and not hitl_drift:
            drift_hitl_fn += 1
        if recall_probe:
            total_recall_probe += 1
        if recall_b1:
            total_recall_b1 += 1
        if orthographic_noise_count:
            orthographic_noise_rows += 1
        if semantic_ambiguity:
            semantic_ambiguity_rows += 1

        s = sector_stats[sector]
        s["count"] += 1
        s["coverage_sum"] += signal.normalization_coverage
        s["drift_scores"][signal.drift_score] += 1
        s["oov_sum"] += signal.oov_token_count
        if hitl_labeled:
            s["hitl_ground_truth"] += 1
        if hitl_drift:
            s["hitl_drift_triggered"] += 1
        if recall_probe:
            s["recall_probe"] += 1
        if recall_b1:
            s["recall_b1"] += 1

    n = max(1, len(arabizi_rows))
    drift_precision_den = drift_hitl_tp + drift_hitl_fp
    drift_recall_den = drift_hitl_tp + drift_hitl_fn

    sector_summary: dict[str, Any] = {}
    for sector, s in sorted(sector_stats.items()):
        c = max(1, s["count"])
        sector_summary[sector] = {
            "count": s["count"],
            "mean_coverage": round(s["coverage_sum"] / c, 4),
            "drift_distribution": s["drift_scores"],
            "mean_oov_count": round(s["oov_sum"] / c, 2),
            "hitl_ground_truth_rate": round(s["hitl_ground_truth"] / c, 4),
            "hitl_drift_trigger_rate": round(s["hitl_drift_triggered"] / c, 4),
            "recall_probe": round(s["recall_probe"] / c, 4),
            "recall_b1_raw": round(s["recall_b1"] / c, 4),
        }

    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "corpus_path": str(reports_path.relative_to(ROOT)),
            "vocab_version": vocab.version,
            "route_confidence_threshold": ROUTE_CONFIDENCE_THRESHOLD,
            "batch": "B001",
            "arabizi_mixed_row_count": len(arabizi_rows),
            "evaluation_scope": "B001 regression smoke test, not final generalization/F1 evidence",
            "methodology_notes": [
                "Vocabulary v1.4.0 includes Batch 001 accepted OOV terms; issue recall is a contract smoke test.",
                "Drift-triggered HITL is language-risk only; full EEP HITL also uses sector, severity, public safety, and calibrated route confidence.",
                "Batch 001 has only 14 Arabizi/mixed rows; use Batch 002+ for reliable per-language model metrics.",
            ],
        },
        "summary": {
            "total_arabizi_mixed_rows": len(arabizi_rows),
            "mean_coverage": round(total_coverage / n, 4),
            "mean_oov_count": round(total_oov / n, 2),
            "drift_distribution": {
                "score_0": drift_dist[0],
                "score_1": drift_dist[1],
                "score_2": drift_dist[2],
                "score_3": drift_dist[3],
            },
            "hitl_labeled_rate": round(total_hitl_labeled / n, 4),
            "hitl_drift_trigger_rate": round(total_hitl_drift / n, 4),
            "drift_vs_hitl_policy_diagnostic": {
                "true_positive_count": drift_hitl_tp,
                "false_positive_count": drift_hitl_fp,
                "false_negative_count": drift_hitl_fn,
                "precision": round(drift_hitl_tp / drift_precision_den, 4) if drift_precision_den else None,
                "recall": round(drift_hitl_tp / drift_recall_den, 4) if drift_recall_den else None,
                "interpretation": "Diagnostic only: language drift is one HITL guard, not the full HITL policy.",
            },
            "issue_type_recall_probe": round(total_recall_probe / n, 4),
            "issue_type_recall_b1_raw": round(total_recall_b1 / n, 4),
            "recall_gain_vs_b1_raw": round((total_recall_probe - total_recall_b1) / n, 4),
            "orthographic_noise_row_rate": round(orthographic_noise_rows / n, 4),
            "semantic_ambiguity_row_rate": round(semantic_ambiguity_rows / n, 4),
        },
        "sector_breakdown": sector_summary,
        "per_row_details": per_row,
    }


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

def print_report(result: dict[str, Any]) -> None:
    meta = result["meta"]
    s = result["summary"]
    n = s["total_arabizi_mixed_rows"]
    drift = s["drift_distribution"]

    sep = "=" * 64
    thin = "-" * 64

    print(f"\n{sep}")
    print(f"  Arabizi Coverage Evaluation  -  Batch {meta['batch']}")
    print(f"  Vocab version : {meta['vocab_version']}")
    print(f"  ROUTE_CONFIDENCE_THRESHOLD : {meta['route_confidence_threshold']}")
    print(f"  Scope : {meta['evaluation_scope']}")
    print(f"  Generated : {meta['generated_at']}")
    print(f"{sep}")

    print(f"\nRows analysed (arabizi/mixed) : {n}")
    print(f"Mean known-term coverage      : {s['mean_coverage']:.1%}")
    print(f"Mean OOV tokens per row       : {s['mean_oov_count']:.2f}")

    print(f"\nDrift score distribution:")
    labels = ["0 - clean", "1 - minor", "2 - meaningful/HITL", "3 - severe"]
    for idx, label in enumerate(labels):
        count = drift[f"score_{idx}"]
        pct = count / n if n else 0.0
        bar = "#" * round(pct * 24)
        print(f"  score={idx}  ({label:<20s}) : {count:2d} ({pct:5.1%})  {bar}")

    print(f"\nHITL rates:")
    print(f"  Labeled ground truth       : {s['hitl_labeled_rate']:.1%}")
    print(f"  Drift-triggered (score >=2): {s['hitl_drift_trigger_rate']:.1%}")
    diag = s["drift_vs_hitl_policy_diagnostic"]
    print(
        "  Drift-vs-HITL diagnostic  : "
        f"TP={diag['true_positive_count']}, FP={diag['false_positive_count']}, "
        f"FN={diag['false_negative_count']}"
    )

    rp = s["issue_type_recall_probe"]
    rb = s["issue_type_recall_b1_raw"]
    gain = s["recall_gain_vs_b1_raw"]
    sign = "+" if gain >= 0 else ""
    print(f"\nIssue-type recall:")
    print(f"  Probe  (with normalization) : {rp:.1%}  ({round(rp * n)}/{n})")
    print(f"  B1 raw (no normalization)   : {rb:.1%}  ({round(rb * n)}/{n})")
    print(f"  Normalization gain          : {sign}{gain:.1%}")
    print(f"  Orthographic-noise rows     : {s['orthographic_noise_row_rate']:.1%}")
    print(f"  Semantic-ambiguity rows     : {s['semantic_ambiguity_row_rate']:.1%}")

    print(f"\n{thin}")
    print(f"  Per-sector breakdown")
    print(f"{thin}")
    hdr = f"  {'Sector':<14}  {'N':>3}  {'Cov':>6}  {'OOV':>4}  " \
          f"{'HITL%':>6}  {'RecPrb':>7}  {'RecB1':>6}"
    print(hdr)
    print(f"  {'-'*14}  {'-'*3}  {'-'*6}  {'-'*4}  {'-'*6}  {'-'*7}  {'-'*6}")
    for sector, sec in sorted(result["sector_breakdown"].items()):
        print(
            f"  {sector:<14}  {sec['count']:>3}  "
            f"{sec['mean_coverage']:>5.1%}  "
            f"{sec['mean_oov_count']:>4.1f}  "
            f"{sec['hitl_ground_truth_rate']:>5.1%}  "
            f"{sec['recall_probe']:>6.1%}  "
            f"{sec['recall_b1_raw']:>5.1%}"
        )

    print(f"\n{thin}")
    print(f"  Per-row diagnostics")
    print(f"{thin}")
    print(
        f"  {'ReportID':<18}  {'Lang':<7}  {'Cov':>4}  "
        f"{'OOV':>3}  {'D':>1}  {'Prb':>3}  {'B1':>2}  "
        f"{'HITL':>4}  Known Terms"
    )
    print(f"  {'-'*18}  {'-'*7}  {'-'*4}  {'-'*3}  {'-'*1}  {'-'*3}  {'-'*2}  {'-'*4}  {'-'*30}")
    for row in result["per_row_details"]:
        rp_s = "Y" if row["recall_probe"] else "N"
        rb_s = "Y" if row["recall_b1_raw"] else "N"
        h_s = "Y" if row["hitl_drift_triggered"] else " "
        terms = row["known_terms"]
        terms_s = ", ".join(terms[:5])
        if len(terms) > 5:
            terms_s += f" +{len(terms) - 5}"
        print(
            f"  {row['report_id']:<18}  {row['language']:<7}  "
            f"{row['coverage']:>3.0%}  "
            f"{row['oov_token_count']:>3}  "
            f"{row['drift_score']:>1}  "
            f"  {rp_s}   {rb_s}    {h_s}   {terms_s}"
        )

    print(f"\n{sep}")
    print(f"  Artifact : {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="C-phase offline evaluation harness for the Arabizi heuristic probe."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Dump JSON to stdout instead of formatted report.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write the JSON artifact to disk.",
    )
    args = parser.parse_args(argv)

    result = evaluate()

    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
