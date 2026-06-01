"""Evaluate CedarFix rules-only vs model-only vs hybrid IEP-1.

This is the professor-facing proof artifact: it quantifies what the learned
classifier adds, what rules alone miss, and why the hybrid HITL gate is safer
than either component alone.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.iep1.extractor import build_issue_intelligence  # noqa: E402
from src.iep1.semantic_classifier import classify_text  # noqa: E402
from src.shared.arabizi_features import analyze_language_signal  # noqa: E402

EVAL_PATHS = (
    # Locked held-out test ONLY. The model trains on batch8_train (see
    # src/iep1/semantic_classifier.py); this file is never used for training, so
    # the reported numbers are leakage-free. Do NOT add the val/train files here.
    ROOT / "data" / "training" / "cidarfix_v29_batch7_model_final_test_locked.jsonl",
)
REPORT_PATH = ROOT / "reports" / "ai_ablation_report_2026-06-01.md"
JSON_PATH = ROOT / "reports" / "ai_ablation_report_2026-06-01.json"


def _split_label(label: str) -> tuple[str, str]:
    sector, issue = label.split("/", 1)
    return sector.upper(), issue.lower()


def _iter_cases(limit: int = 1000):
    seen = 0
    for path in EVAL_PATHS:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if seen >= limit:
                    return
                row = json.loads(line)
                label = (row.get("metadata") or {}).get("label")
                if not label or "/" not in label:
                    continue
                text = ""
                for message in row.get("messages", []):
                    if message.get("role") == "user":
                        text = str(message.get("content") or "")
                        break
                if not text:
                    continue
                seen += 1
                yield {"id": (row.get("metadata") or {}).get("uuid"), "text": text, "label": label}


def _empty_stats() -> dict:
    return {
        "n": 0,
        "sector_correct": 0,
        "label_correct": 0,
        "false_auto_route": 0,
        "hitl_or_review": 0,
        "auto_route_total": 0,
        "auto_route_sector_correct": 0,
        "per_sector": defaultdict(lambda: {"n": 0, "correct": 0}),
    }


def _record(stats: dict, *, expected_sector: str, expected_label: str, pred_sector: str, pred_label: str, auto_route: bool) -> None:
    stats["n"] += 1
    sector_ok = pred_sector == expected_sector
    label_ok = pred_label == expected_label
    stats["sector_correct"] += int(sector_ok)
    stats["label_correct"] += int(label_ok)
    stats["false_auto_route"] += int(auto_route and not sector_ok)
    stats["hitl_or_review"] += int(not auto_route)
    stats["auto_route_total"] += int(auto_route)
    stats["auto_route_sector_correct"] += int(auto_route and sector_ok)
    stats["per_sector"][expected_sector]["n"] += 1
    stats["per_sector"][expected_sector]["correct"] += int(sector_ok)


def _pct(num: int, denom: int) -> float:
    return round(num / denom, 4) if denom else 0.0


def _summarize(name: str, stats: dict) -> dict:
    n = stats["n"]
    per_sector = {
        sector: _pct(values["correct"], values["n"])
        for sector, values in sorted(stats["per_sector"].items())
    }
    return {
        "system": name,
        "n": n,
        "sector_accuracy": _pct(stats["sector_correct"], n),
        "label_accuracy": _pct(stats["label_correct"], n),
        "false_auto_route": stats["false_auto_route"],
        "review_rate": _pct(stats["hitl_or_review"], n),
        "auto_route_coverage": _pct(stats["auto_route_total"], n),
        "auto_route_precision": _pct(
            stats["auto_route_sector_correct"], stats["auto_route_total"]
        ),
        "auto_route_total": stats["auto_route_total"],
        "per_sector_accuracy": per_sector,
    }


def evaluate(limit: int = 1000) -> dict:
    stats = {
        "rules_only": _empty_stats(),
        "model_only": _empty_stats(),
        "hybrid": _empty_stats(),
    }
    confusion = Counter()

    for case in _iter_cases(limit):
        expected_sector, expected_issue = _split_label(case["label"])
        expected_label = f"{expected_sector}/{expected_issue}"
        signal = analyze_language_signal(raw_text=case["text"], report_id=case["id"])

        rules = build_issue_intelligence(signal, use_model=False)
        rules_sector = rules["routing_sector"]
        rules_label = f"{rules_sector}/{rules['issue_type']}"
        _record(
            stats["rules_only"],
            expected_sector=expected_sector,
            expected_label=expected_label,
            pred_sector=rules_sector,
            pred_label=rules_label,
            auto_route=rules["review_recommendation"] == "AUTO_ROUTE_ELIGIBLE",
        )

        model = classify_text(case["text"])
        selected = model.selected
        model_sector = selected.sector if selected else "OTHER"
        model_issue = selected.issue_type if selected else "UNCLASSIFIED"
        model_conf = selected.confidence if selected else 0.0
        _record(
            stats["model_only"],
            expected_sector=expected_sector,
            expected_label=expected_label,
            pred_sector=model_sector,
            pred_label=f"{model_sector}/{model_issue}",
            auto_route=model_conf >= 0.65,
        )

        hybrid = build_issue_intelligence(signal, use_model=True)
        hybrid_sector = hybrid["routing_sector"]
        _record(
            stats["hybrid"],
            expected_sector=expected_sector,
            expected_label=expected_label,
            pred_sector=hybrid_sector,
            pred_label=f"{hybrid_sector}/{hybrid['issue_type']}",
            auto_route=hybrid["review_recommendation"] == "AUTO_ROUTE_ELIGIBLE",
        )
        if hybrid_sector != expected_sector:
            confusion[(expected_sector, hybrid_sector)] += 1

    summaries = {name: _summarize(name, value) for name, value in stats.items()}
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "summaries": summaries,
        "hybrid_confusions": [
            {"expected": exp, "predicted": pred, "count": count}
            for (exp, pred), count in confusion.most_common(20)
        ],
    }


def write_report(result: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for summary in result["summaries"].values():
        rows.append(
            "| {system} | {n} | {sector:.1%} | {label:.1%} | {review:.1%} | "
            "{coverage:.1%} | {precision:.1%} | {false_auto} |".format(
                system=summary["system"],
                n=summary["n"],
                sector=summary["sector_accuracy"],
                label=summary["label_accuracy"],
                review=summary["review_rate"],
                coverage=summary["auto_route_coverage"],
                precision=summary["auto_route_precision"],
                false_auto=summary["false_auto_route"],
            )
        )
    md = [
        "# CedarFix AI Ablation Report",
        "",
        f"Generated: {result['generated']}",
        "",
        "Systems compared:",
        "",
        "- Rules-only: production vocabulary/keyword baseline.",
        "- Model-only: learned hashed char-gram classifier over noisy multilingual text.",
        "- Hybrid: model + rules arbitration with HITL on disagreement and low confidence.",
        "",
        "Eval set: **locked held-out test only** "
        "(`cidarfix_v29_batch7_model_final_test_locked.jsonl`). The learned model "
        "trains on `batch8_train` only, so these numbers are leakage-free.",
        "",
        "Auto-route **coverage** = share of cases the system auto-routes without HITL. "
        "Auto-route **precision** = sector accuracy *within* those auto-routed cases. "
        "The hybrid goal is high auto-route precision at safe coverage, not raw accuracy.",
        "",
        "| System | N | Sector acc | Label acc | Review/HITL | Auto-route coverage | Auto-route precision | False auto-routes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "Top hybrid confusions:",
        "",
    ]
    if result["hybrid_confusions"]:
        for item in result["hybrid_confusions"]:
            md.append(f"- {item['expected']} -> {item['predicted']}: {item['count']}")
    else:
        md.append("- None in evaluated sample.")
    md.append("")
    md.append("Interpretation: CedarFix should present the hybrid row, not a standalone model claim. The model provides semantic reach; rules and HITL provide safety.")
    REPORT_PATH.write_text("\n".join(md), encoding="utf-8")
    JSON_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    out = evaluate()
    write_report(out)
    print(f"wrote {REPORT_PATH}")
