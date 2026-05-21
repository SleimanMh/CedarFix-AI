"""
Build a high-volume Arabizi surface-form layer from reviewed/staged assets.

This file deliberately does not expand the production vocabulary. It creates a
review-only normalization/OOV/stress-test layer with many spelling variants
derived from existing CedarFix sources.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARABIZI = ROOT / "data" / "knowledge_base" / "arabizi"
OUT = ARABIZI / "arabizi_surface_forms_v15.csv"
RELIABILITY = ARABIZI / "arabizi_reliability_layer.json"

BLOCKED_USES = "routing|severity_assignment|sector_classification|issue_type_decision|core_vocab_promotion"
ALLOWED_USES = "normalization_support|oov_detection|duplicate_matching_support|language_detection_features|stress_test_generation"
CREATED_AT = "2026-05-21T00:00:00Z"
MAX_ROWS = 10000

FIELDS = [
    "surface_id",
    "surface_form",
    "normalized_surface",
    "canonical_form",
    "source_layer",
    "source_id",
    "source_field",
    "sector",
    "issue_type",
    "category",
    "variant_rule",
    "confidence_level",
    "false_friend_risk",
    "risk_level",
    "allowed_uses",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "must_not_auto_promote",
    "source_reference",
    "created_at",
]


@dataclass(frozen=True)
class Seed:
    form: str
    canonical: str
    source_layer: str
    source_id: str
    source_field: str
    sector: str
    issue_type: str
    category: str
    source_reference: str
    risk_level: str
    false_friend_risk: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def split_variants(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;|]", raw or "") if part.strip()]


def norm(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def compact(text: str) -> str:
    return re.sub(r"[\s_'\-]", "", text)


def add_seed(seeds: list[Seed], **kwargs: str) -> None:
    form = norm(kwargs["form"])
    canonical = norm(kwargs.get("canonical") or form)
    if not form:
        return
    seeds.append(
        Seed(
            form=form,
            canonical=canonical,
            source_layer=kwargs.get("source_layer", ""),
            source_id=kwargs.get("source_id", ""),
            source_field=kwargs.get("source_field", "variants"),
            sector=kwargs.get("sector", "ALL") or "ALL",
            issue_type=kwargs.get("issue_type", "ALL_SUPPORT") or "ALL_SUPPORT",
            category=kwargs.get("category", ""),
            source_reference=kwargs.get("source_reference", ""),
            risk_level=kwargs.get("risk_level", "LOW") or "LOW",
            false_friend_risk=kwargs.get("false_friend_risk", "false").lower(),
        )
    )


def load_seeds() -> list[Seed]:
    seeds: list[Seed] = []

    # Highest-priority safety layers first so they are never pushed out by the
    # 10k cap.
    for row in read_csv(ARABIZI / "arabizi_stoplist.csv"):
        for value in {row.get("term", ""), row.get("normalized_term", "")}:
            add_seed(
                seeds,
                form=value,
                canonical=row.get("normalized_term", "") or value,
                source_layer="stoplist",
                source_id=row.get("normalized_term", "") or row.get("term", ""),
                source_field="term",
                sector="ALL",
                issue_type="STOPLIST",
                category="stoplist",
                source_reference=row.get("source_reference", ""),
                risk_level=row.get("risk_level", "HIGH"),
                false_friend_risk="true",
            )

    for row in read_csv(ARABIZI / "arabizi_protected_combos.csv"):
        canonical = row.get("romanized_canonical", "")
        add_seed(
            seeds,
            form=canonical,
            canonical=canonical,
            source_layer="protected_combos",
            source_id=row.get("combo_id", ""),
            source_field="romanized_canonical",
            sector=row.get("combined_sector", "ALL"),
            issue_type=row.get("combined_issue_type", "ALL_SUPPORT"),
            category=row.get("override_type", ""),
            source_reference=row.get("source_reference", ""),
            risk_level="HIGH",
            false_friend_risk=row.get("false_friend_risk", "true"),
        )

    for row in read_csv(ARABIZI / "arabizi_general_word_bank.csv"):
        canonical = row.get("romanized_canonical", "")
        values = [canonical, *split_variants(row.get("variants", ""))]
        for value in values:
            add_seed(
                seeds,
                form=value,
                canonical=canonical or value,
                source_layer="general_word_bank",
                source_id=row.get("word_id", ""),
                sector="ALL",
                issue_type="ALL_SUPPORT",
                category=row.get("category", ""),
                source_reference=row.get("source_reference", ""),
                risk_level="LOW",
                false_friend_risk=row.get("false_friend_risk", "false"),
            )

    for row in read_csv(ARABIZI / "arabizi_candidate_bank.csv"):
        values = split_variants(row.get("variants", ""))
        canonical = values[0] if values else row.get("english", "")
        for value in values:
            add_seed(
                seeds,
                form=value,
                canonical=canonical or value,
                source_layer="candidate_bank",
                source_id=row.get("candidate_id", ""),
                sector=row.get("sector", ""),
                issue_type=row.get("issue_type", ""),
                category=row.get("category", ""),
                source_reference=row.get("source_reference", ""),
                risk_level=row.get("risk_level", "MEDIUM"),
                false_friend_risk=row.get("false_friend_risk", "false"),
            )

    for row in read_csv(ARABIZI / "arabizi_candidate_bank_quarantine.csv"):
        values = split_variants(row.get("variants", ""))
        canonical = values[0] if values else row.get("english", "")
        for value in values:
            add_seed(
                seeds,
                form=value,
                canonical=canonical or value,
                source_layer="candidate_bank_quarantine",
                source_id=row.get("candidate_id", ""),
                sector=row.get("sector", "ALL"),
                issue_type=row.get("issue_type", "ALL_SUPPORT"),
                category=row.get("category", ""),
                source_reference=f"{row.get('source_reference','')}|quarantine:{row.get('cleanup_reason','')}",
                risk_level="MEDIUM",
                false_friend_risk="true",
            )

    # NOTE: stoplist and protected_combos are intentionally loaded only once
    # (at the top of this function) so they get priority placement before the
    # 10k cap without creating duplicate seeds.

    return seeds


def replace_once(text: str, old: str, new: str) -> str | None:
    if old not in text:
        return None
    changed = text.replace(old, new, 1)
    return changed if changed != text else None


def generate_forms(seed: Seed) -> list[tuple[str, str, str, str]]:
    """Return (form, rule, confidence, false_friend)."""
    base = seed.form
    generated: list[tuple[str, str, str, str]] = [(base, "BASE_SOURCE_FORM", "HIGH", seed.false_friend_risk)]

    c = compact(base)
    if c and c != base:
        generated.append((c, "REMOVE_SPACES_PUNCT", "MEDIUM", "true"))

    if " " in base:
        generated.append((base.replace(" ", "-"), "SPACE_TO_HYPHEN", "MEDIUM", seed.false_friend_risk))
        generated.append((base.replace(" ", ""), "SPACELESS_PHRASE", "MEDIUM", "true"))

    if base.startswith("l "):
        generated.append((base[2:], "DROP_L_ARTICLE", "MEDIUM", "true"))
    if base.startswith("el "):
        generated.append((base[3:], "DROP_EL_ARTICLE", "MEDIUM", "true"))
    if not base.startswith(("l ", "el ", "al ")) and len(base) > 3 and " " not in base:
        generated.append((f"l {base}", "ADD_L_ARTICLE", "MEDIUM", "true"))
        generated.append((f"el {base}", "ADD_EL_ARTICLE", "LOW", "true"))

    rules = [
        ("ou", "u", "OU_TO_U", "MEDIUM"),
        ("u", "ou", "U_TO_OU", "LOW"),
        ("ee", "i", "EE_TO_I", "MEDIUM"),
        ("i", "ee", "I_TO_EE", "LOW"),
        ("sh", "ch", "SH_TO_CH", "MEDIUM"),
        ("ch", "sh", "CH_TO_SH", "MEDIUM"),
        ("kh", "5", "KH_TO_5", "HIGH"),
        ("5", "kh", "5_TO_KH", "HIGH"),
        ("gh", "8", "GH_TO_8", "MEDIUM"),
        ("8", "gh", "8_TO_GH", "MEDIUM"),
        ("2", "'", "2_TO_APOSTROPHE", "MEDIUM"),
        ("'", "2", "APOSTROPHE_TO_2", "MEDIUM"),
        ("7", "h", "7_TO_H_LOW_CONF", "LOW"),
        ("h", "7", "H_TO_7_LOW_CONF", "LOW"),
        ("aa", "a", "AA_TO_A", "MEDIUM"),
    ]
    for old, new, rule, confidence in rules:
        changed = replace_once(base, old, new)
        if changed:
            generated.append((changed, rule, confidence, "true" if confidence == "LOW" else seed.false_friend_risk))

    # Collapse repeated Latin characters, common in chat emphasis.
    collapsed = re.sub(r"([a-z])\1{2,}", r"\1\1", base)
    if collapsed != base:
        generated.append((collapsed, "COLLAPSE_CHAT_REPETITION", "MEDIUM", seed.false_friend_risk))

    # De-duplicate while preserving rule priority.
    seen: set[str] = set()
    out: list[tuple[str, str, str, str]] = []
    for form, rule, confidence, ff in generated:
        form = norm(form)
        if not form or form in seen:
            continue
        seen.add(form)
        out.append((form, rule, confidence, "true" if ff.lower() in {"true", "yes"} else "false"))
    return out[:18]


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for seed in load_seeds():
        for form, rule, confidence, ff in generate_forms(seed):
            key = (form, seed.canonical, seed.source_layer, seed.source_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(
                {
                    "surface_id": f"ASF-{len(rows)+1:05d}",
                    "surface_form": form,
                    "normalized_surface": norm(form),
                    "canonical_form": seed.canonical,
                    "source_layer": seed.source_layer,
                    "source_id": seed.source_id,
                    "source_field": seed.source_field,
                    "sector": seed.sector,
                    "issue_type": seed.issue_type,
                    "category": seed.category,
                    "variant_rule": rule,
                    "confidence_level": confidence,
                    "false_friend_risk": ff,
                    "risk_level": seed.risk_level if seed.risk_level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM",
                    "allowed_uses": ALLOWED_USES if seed.source_layer != "stoplist" else "stoplist_filtering|oov_suppression",
                    "blocked_uses": BLOCKED_USES,
                    "review_status": "REVIEW_ONLY_GENERATED",
                    "reviewer_id": "SYSTEM-V15",
                    "must_not_auto_promote": "true",
                    "source_reference": seed.source_reference,
                    "created_at": CREATED_AT,
                }
            )
            if len(rows) >= MAX_ROWS:
                return rows
    return rows


def update_reliability_layer(row_count: int) -> None:
    if not RELIABILITY.exists():
        return
    data = json.loads(RELIABILITY.read_text(encoding="utf-8"))
    metadata = data.setdefault("metadata", {})
    metadata["version"] = "v1.5-v15-surface-form-expansion"
    metadata["updated_at_utc"] = utc_now()
    counts = metadata.setdefault("section_row_counts", {})
    counts["surface_forms_v15_csv"] = row_count
    # Sync stale CSV counts from csv_file_registry so section_row_counts stays
    # consistent even when called after V14 absorbed more rows.
    registry_snapshot = metadata.get("csv_file_registry", {})
    for csv_key in ("arabizi_general_word_bank.csv", "arabizi_protected_combos.csv",
                    "arabizi_stoplist.csv", "arabizi_candidate_bank.csv",
                    "arabizi_candidate_bank_quarantine.csv"):
        entry = registry_snapshot.get(csv_key, {})
        if entry.get("row_count"):
            count_key = csv_key.replace("arabizi_", "").replace(".csv", "_csv")
            counts[count_key] = entry["row_count"]
    registry = metadata.setdefault("csv_file_registry", {})
    registry["arabizi_surface_forms_v15.csv"] = {
        "path": "data/knowledge_base/arabizi/arabizi_surface_forms_v15.csv",
        "row_count": row_count,
        "sources": [
            "arabizi_general_word_bank.csv",
            "arabizi_candidate_bank.csv",
            "arabizi_candidate_bank_quarantine.csv",
            "arabizi_protected_combos.csv",
            "arabizi_stoplist.csv",
        ],
        "rule": "review-only generated surface forms; blocked from routing, severity, sector, issue, and core vocabulary promotion",
        "version": "V15_SURFACE_FORM_EXPANSION",
    }
    metadata["v15_surface_form_expansion"] = {
        "row_count": row_count,
        "target_use": "normalization, OOV detection, duplicate matching support, language detection features, stress tests",
        "guardrail": "No row may directly drive routing/severity/sector/issue decisions or core vocabulary promotion.",
        "internet_research_policy": "External Arabizi resources are documented for future licensed ingestion; V15 itself derives variants only from existing CedarFix assets.",
    }
    RELIABILITY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_rows()
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    update_reliability_layer(len(rows))
    print(f"Wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
