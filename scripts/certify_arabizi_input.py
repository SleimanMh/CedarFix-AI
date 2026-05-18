#!/usr/bin/env python3
"""Live Arabizi reliability certificate for a single CedarFix input.

This is the demo-facing layer above the fixed Stress Lab. It accepts one live
citizen-style report, generates deterministic noisy variants, runs the same
IEP-1 contract logic on every variant, and writes:

- JSON evidence for MLflow / audit
- standalone HTML report for presentation

It is a reliability certificate, not a model benchmark. The certificate answers:
"Does the operational decision survive plausible Lebanese Arabizi typing noise,
and does uncertainty become visible when it should?"
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.iep1.extractor import extract  # noqa: E402

DEFAULT_TEXT = "fi jora kbire 3al tari2 w l wad3 m5atra ktir"
DEFAULT_LANGUAGE = "arabizi"
JSON_OUTPUT = ROOT / "data" / "eval" / "arabizi_reliability_certificate_v1.json"
HTML_OUTPUT = ROOT / "data" / "eval" / "arabizi_reliability_certificate_v1.html"
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
CERTIFICATE_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def perturbations(text: str) -> list[dict[str, str]]:
    """Return deterministic adversarial variants for live demo certification."""

    clean = collapse_spaces(text)
    variants: list[dict[str, str]] = [
        {
            "variant_id": "live_original",
            "perturbation": "original input",
            "text": clean,
        }
    ]

    transforms: list[tuple[str, str]] = []

    digit_omitted = (
        clean.replace("7ofra", "hofra")
        .replace("7afra", "hafra")
        .replace("7amra", "hamra")
        .replace("5atar", "khatar")
    )
    if digit_omitted != clean:
        transforms.append(("digit omission / plain-letter substitution", digit_omitted))

    repeated = re.sub(r"\b(jora|joura|hofra|7ofra|may|sarif|silk|transformateur)\b", r"\1aaaa", clean, count=1)
    if repeated != clean:
        transforms.append(("repeated letters", repeated))

    panic = f"5tr444444 {clean}"
    transforms.append(("panic shorthand prefix", panic))

    fused = re.sub(r"\bfi\s+([a-z0-9]+)\s+", r"fi\1", clean, count=1, flags=re.I)
    if fused != clean:
        transforms.append(("mobile no-space fusion", fused))

    punctuation = clean.replace(" ", "!!! ", 2)
    if punctuation != clean:
        transforms.append(("punctuation/noise injection", punctuation))

    fr_mix = clean
    if "jora" in clean or "hofra" in clean or "7ofra" in clean:
        fr_mix = f"route dangereuse: {clean}"
    elif "transformateur" in clean:
        fr_mix = f"{clean}, situation critique"
    elif "may" in clean or "sarif" in clean:
        fr_mix = f"{clean}, odeur tres forte"
    else:
        fr_mix = f"{clean}, situation critique"
    transforms.append(("French/English code switch", fr_mix))

    dropped_marker = re.sub(r"[2357]", "", clean, count=2)
    if dropped_marker and dropped_marker != clean:
        transforms.append(("dropped first Arabizi marker digits", dropped_marker))

    seen = {clean}
    for idx, (name, candidate) in enumerate(transforms, start=1):
        candidate = collapse_spaces(candidate)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants.append(
            {
                "variant_id": f"live_variant_{idx:02d}",
                "perturbation": name,
                "text": candidate,
            }
        )

    return variants


def evaluate_variant(variant: dict[str, str], *, language_hint: str) -> dict[str, Any]:
    result = extract(
        variant["variant_id"],
        variant["text"],
        language_hint,
        include_embedding=False,
    )
    signal = result["iep1_signal_json"]
    return {
        "variant_id": variant["variant_id"],
        "perturbation": variant["perturbation"],
        "text": variant["text"],
        "routing_sector": result["routing_sector"],
        "issue_type": result["issue_type"],
        "issue_type_confidence": result["issue_type_confidence"],
        "drift_score": result["drift_score"],
        "force_hitl": bool(signal.get("drift_score", 0) >= 2 or result["issue_type_confidence"] < 0.65),
        "normalization_coverage": signal["normalization_coverage"],
        "code_mix_ratio": signal["code_mix_ratio"],
        "arabizi_marker_density": signal["arabizi_marker_density"],
        "oov_token_count": signal["oov_token_count"],
        "oov_high_risk_count": signal["oov_high_risk_count"],
        "oov_tokens": [token["token"] for token in signal["oov_tokens"]],
        "known_terms": signal["known_terms"],
        "orthographic_noise_count": int(signal["explanation_features"].get("orthographic_noise_count", 0)),
        "semantic_ambiguity": bool(signal["explanation_features"].get("semantic_ambiguity", False)),
    }


def build_certificate(text: str, language_hint: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    variants = perturbations(text)
    rows = [evaluate_variant(variant, language_hint=language_hint) for variant in variants]
    original = rows[0]
    expected_sector = original["routing_sector"]
    expected_issue = original["issue_type"]
    for row in rows:
        row["stable_sector"] = row["routing_sector"] == expected_sector
        row["stable_issue"] = row["issue_type"] == expected_issue
        row["same_decision"] = row["stable_sector"] and row["stable_issue"]

    total = max(1, len(rows))
    drift_distribution = {f"score_{idx}": 0 for idx in range(4)}
    for row in rows:
        drift_distribution[f"score_{row['drift_score']}"] += 1

    stable_sector_rate = sum(row["stable_sector"] for row in rows) / total
    stable_issue_rate = sum(row["stable_issue"] for row in rows) / total
    hitl_rate = sum(row["force_hitl"] for row in rows) / total
    oov_union = sorted({token for row in rows for token in row["oov_tokens"]})
    brittle_rows = [row for row in rows if not row["same_decision"]]
    reliability_grade = "A"
    if stable_sector_rate < 0.9:
        reliability_grade = "C"
    elif stable_issue_rate < 0.75:
        reliability_grade = "B"

    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "certificate_version": CERTIFICATE_VERSION,
            "script": "scripts/certify_arabizi_input.py",
            "json_artifact": str(JSON_OUTPUT.relative_to(ROOT)),
            "html_artifact": str(HTML_OUTPUT.relative_to(ROOT)),
            "vocab_sha256": sha256_file(VOCAB_PATH),
            "language_hint": language_hint,
            "scope": "single-input live robustness certificate, not final corpus evaluation",
        },
        "original_decision": {
            "text": original["text"],
            "routing_sector": expected_sector,
            "issue_type": expected_issue,
            "issue_type_confidence": original["issue_type_confidence"],
            "force_hitl": original["force_hitl"],
            "drift_score": original["drift_score"],
        },
        "summary": {
            "variant_count": len(rows),
            "stable_sector_rate": round(stable_sector_rate, 4),
            "stable_issue_rate": round(stable_issue_rate, 4),
            "hitl_rate": round(hitl_rate, 4),
            "mean_coverage": round(sum(row["normalization_coverage"] for row in rows) / total, 4),
            "mean_oov_count": round(sum(row["oov_token_count"] for row in rows) / total, 2),
            "max_drift_score": max(row["drift_score"] for row in rows),
            "drift_distribution": drift_distribution,
            "unique_oov_tokens": oov_union,
            "brittle_variant_count": len(brittle_rows),
            "reliability_grade": reliability_grade,
        },
        "recommended_review_actions": recommend_actions(rows),
        "variants": rows,
    }


def recommend_actions(rows: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    oov = sorted({token for row in rows for token in row["oov_tokens"]})
    if oov:
        actions.append(f"Review OOV candidates before promotion: {', '.join(oov)}")
    if any(not row["same_decision"] for row in rows):
        actions.append("Inspect brittle variants where issue_type changed under perturbation.")
    if any(row["semantic_ambiguity"] for row in rows):
        actions.append("Keep HITL enabled for semantic ambiguity cases.")
    if not actions:
        actions.append("No immediate review action; keep artifact as MLflow evidence.")
    return actions


def pct(value: float) -> str:
    return f"{value:.1%}"


def bar(value: float) -> str:
    width = max(1, min(100, int(round(value * 100))))
    return f"<span class='bar'><span style='width:{width}%'></span></span>"


def render_html(cert: dict[str, Any]) -> str:
    summary = cert["summary"]
    original = cert["original_decision"]
    rows = cert["variants"]
    actions = cert["recommended_review_actions"]
    row_html = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['variant_id'])}</td>"
        f"<td>{html.escape(row['perturbation'])}<br><small>{html.escape(row['text'])}</small></td>"
        f"<td>{html.escape(row['routing_sector'])}/{html.escape(row['issue_type'])}</td>"
        f"<td>{row['issue_type_confidence']:.2f}</td>"
        f"<td>{row['drift_score']}</td>"
        f"<td>{pct(row['normalization_coverage'])}</td>"
        f"<td>{'yes' if row['force_hitl'] else 'no'}</td>"
        f"<td>{', '.join(html.escape(token) for token in row['oov_tokens']) or '-'}</td>"
        f"<td>{'OK' if row['same_decision'] else 'CHECK'}</td>"
        "</tr>"
        for row in rows
    )
    action_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in actions)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CedarFix Arabizi Reliability Certificate</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f7f8fa; color: #17202a; }}
    header {{ background: #102033; color: #fff; padding: 28px 40px; }}
    header h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    header p {{ margin: 0; color: #d6e2f0; }}
    main {{ padding: 28px 40px 48px; }}
    section {{ margin: 0 0 28px; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .metric {{ background: #fff; border: 1px solid #d9e0e8; padding: 14px; border-radius: 6px; }}
    .label {{ color: #5d6d7e; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .bar {{ display: block; height: 8px; background: #e8edf2; margin-top: 8px; border-radius: 99px; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; background: #167a68; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9e0e8; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e6ebf0; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f7; font-size: 12px; text-transform: uppercase; color: #435466; }}
    small {{ color: #5d6d7e; display: block; max-width: 560px; margin-top: 4px; }}
    .decision {{ background: #fff; border-left: 4px solid #167a68; padding: 14px 16px; }}
    .actions {{ background: #fff7e6; border: 1px solid #ead7aa; padding: 14px 16px; }}
  </style>
</head>
<body>
  <header>
    <h1>CedarFix Arabizi Reliability Certificate</h1>
    <p>{html.escape(cert['meta']['scope'])}</p>
  </header>
  <main>
    <section class="decision">
      <h2>Original Decision</h2>
      <strong>{html.escape(original['routing_sector'])} / {html.escape(original['issue_type'])}</strong>
      <p>{html.escape(original['text'])}</p>
    </section>
    <section>
      <h2>Reliability Summary</h2>
      <div class="metrics">
        <div class="metric"><div class="label">Grade</div><div class="value">{summary['reliability_grade']}</div></div>
        <div class="metric"><div class="label">Stable Sector</div><div class="value">{pct(summary['stable_sector_rate'])}</div>{bar(summary['stable_sector_rate'])}</div>
        <div class="metric"><div class="label">Stable Issue</div><div class="value">{pct(summary['stable_issue_rate'])}</div>{bar(summary['stable_issue_rate'])}</div>
        <div class="metric"><div class="label">HITL Rate</div><div class="value">{pct(summary['hitl_rate'])}</div>{bar(summary['hitl_rate'])}</div>
        <div class="metric"><div class="label">Mean Coverage</div><div class="value">{pct(summary['mean_coverage'])}</div>{bar(summary['mean_coverage'])}</div>
        <div class="metric"><div class="label">Max Drift</div><div class="value">{summary['max_drift_score']}</div></div>
      </div>
    </section>
    <section class="actions">
      <h2>Recommended Review Actions</h2>
      <ul>{action_items}</ul>
    </section>
    <section>
      <h2>Variant Evidence</h2>
      <table>
        <thead>
          <tr>
            <th>Variant</th><th>Perturbation</th><th>Decision</th><th>Conf</th>
            <th>Drift</th><th>Coverage</th><th>HITL</th><th>OOV</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          {row_html}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def save_outputs(cert: dict[str, Any], *, json_path: Path, html_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(cert, indent=2, ensure_ascii=False), encoding="utf-8")
    html_path.write_text(render_html(cert), encoding="utf-8")


def print_report(cert: dict[str, Any], *, saved: bool = True) -> None:
    s = cert["summary"]
    original = cert["original_decision"]
    print("\n" + "=" * 72)
    print("  CedarFix Live Arabizi Reliability Certificate")
    print("=" * 72)
    print(f"Original decision : {original['routing_sector']} / {original['issue_type']}")
    print(f"Reliability grade : {s['reliability_grade']}")
    print(f"Stable sector     : {pct(s['stable_sector_rate'])}")
    print(f"Stable issue      : {pct(s['stable_issue_rate'])}")
    print(f"HITL rate         : {pct(s['hitl_rate'])}")
    print(f"Mean coverage     : {pct(s['mean_coverage'])}")
    print(f"Unique OOV        : {', '.join(s['unique_oov_tokens']) or 'none'}")
    if saved:
        print(f"JSON artifact     : {JSON_OUTPUT.relative_to(ROOT)}")
        print(f"HTML artifact     : {HTML_OUTPUT.relative_to(ROOT)}")
    else:
        print("Artifacts         : not written (--no-save)")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a live CedarFix Arabizi reliability certificate.")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Raw complaint text to certify.")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="Language hint, usually arabizi or mixed.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write JSON/HTML artifacts.")
    args = parser.parse_args(argv)

    cert = build_certificate(args.text, args.language)
    if not args.no_save:
        save_outputs(cert, json_path=JSON_OUTPUT, html_path=HTML_OUTPUT)

    if args.json:
        print(json.dumps(cert, indent=2, ensure_ascii=False))
    else:
        print_report(cert, saved=not args.no_save)
    return 0


if __name__ == "__main__":
    sys.exit(main())
