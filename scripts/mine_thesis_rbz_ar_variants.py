"""
mine_thesis_rbz_ar_variants.py
================================
V19b — Mine civic term variants from Taha Tobaili's Arabizi-Arabic
translation matrix (rbz-ar.txt). Finds arabizi spellings of civic Arabic
roots not yet present in arabizi_vocabulary.json.

Source:
    data/external_sources/manual_drop/thesis_extracted/thesis/Misc/
    Arabizi-Arabic-Translation-Matrices/rbz-ar.txt

Format of rbz-ar.txt: one entry per line — "arabizi_form arabic_word"
(space separated; arabizi form may contain digits 2/3/5/6/7/8).

The script:
  1. Parses rbz-ar.txt into arabizi→arabic pairs
  2. For each civic Arabic root, collects all matching arabizi forms
  3. Normalises forms and compares against existing vocab
  4. Writes a patch report CSV (always)
  5. With --apply, promotes clean new forms into term_metadata (v1.5.8)

Run:
    python scripts/mine_thesis_rbz_ar_variants.py            # report only
    python scripts/mine_thesis_rbz_ar_variants.py --apply    # apply patch
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
RBZ_AR_PATH = (
    ROOT
    / "data/external_sources/manual_drop/thesis_extracted/thesis/Misc"
    / "Arabizi-Arabic-Translation-Matrices/rbz-ar.txt"
)
REPORT_PATH = ROOT / "data" / "knowledge_base" / "arabizi" / "rbz_ar_civic_variants_report.csv"

NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
NEW_VERSION = "1.5.8"

# ---------------------------------------------------------------------------
# Civic Arabic roots to search for.
# Key   = vocab term_metadata key (None = propose new entry)
# Value = dict with arabic substring(s), English label, sector
# GUARDRAIL: 'خطر' (danger) intentionally EXCLUDED — HIGH_RISK_HINTS
# ---------------------------------------------------------------------------
CIVIC_TARGETS: list[dict] = [
    # ELECTRICITY
    {"key": "kahrabe",         "arabic": ["كهرب"],              "label": "electricity/kahraba",   "sector": "ELECTRICITY"},
    {"key": "3atal",           "arabic": ["عطل", "خلل"],         "label": "breakdown/fault",       "sector": "ELECTRICITY"},
    {"key": "silk_el_kahraba", "arabic": ["سلك"],                "label": "wire/cable",            "sector": "ELECTRICITY"},
    {"key": None,              "arabic": ["محول", "ترانسفورمر"],"label": "transformer",           "sector": "ELECTRICITY"},
    {"key": None,              "arabic": ["عمود", "كهرباء"],     "label": "electricity pole",      "sector": "ELECTRICITY"},
    {"key": None,              "arabic": ["انقطاع"],             "label": "outage/interruption",   "sector": "ELECTRICITY"},
    # ROADS
    {"key": "tarik",           "arabic": ["طريق", "طرق"],        "label": "road/tariq",            "sector": "ROADS"},
    {"key": "tarik",           "arabic": ["شارع"],               "label": "street/share3",         "sector": "ROADS"},
    {"key": "7ufra",           "arabic": ["حفرة", "حفر"],        "label": "pothole/hole",          "sector": "ROADS"},
    {"key": "zeft",            "arabic": ["زفت", "قير"],         "label": "asphalt/tar",           "sector": "ROADS"},
    {"key": None,              "arabic": ["رصيف"],               "label": "sidewalk/pavement",     "sector": "ROADS"},
    {"key": None,              "arabic": ["جسر"],                "label": "bridge",                "sector": "ROADS"},
    # WATER
    {"key": "mayye",           "arabic": ["مياه", "ماء", "مي "], "label": "water",                 "sector": "WATER"},
    {"key": None,              "arabic": ["تسرب", "تسريب"],      "label": "leak/leakage",          "sector": "WATER"},
    {"key": None,              "arabic": ["صرف صحي", "مجار"],    "label": "sewage/drainage",       "sector": "WATER"},
    # WASTE
    {"key": "zibele",          "arabic": ["زبال", "نفايات", "قمامة"], "label": "garbage/waste",    "sector": "WASTE"},
    {"key": "ri7a_besh3a",     "arabic": ["ريحة", "رائحة"],      "label": "bad smell",             "sector": "WASTE"},
    # FLOODING
    {"key": "fayadan",         "arabic": ["فيضان", "فيض"],       "label": "flood/overflow",        "sector": "FLOODING"},
    {"key": "ghare2",          "arabic": ["غرق"],                "label": "drowning/flood",        "sector": "FLOODING"},
    {"key": "matar",           "arabic": ["مطر"],                "label": "rain",                  "sector": "FLOODING"},
    {"key": None,              "arabic": ["نهر", "وادي"],        "label": "river/valley",          "sector": "FLOODING"},
    # SAFETY
    {"key": "sakef",           "arabic": ["سقف"],                "label": "ceiling/roof",          "sector": "SAFETY"},
    {"key": "nar",             "arabic": ["حريق", "حرق"],        "label": "fire",                  "sector": "SAFETY"},
    {"key": None,              "arabic": ["انهيار", "انهار"],    "label": "collapse",              "sector": "SAFETY"},
    {"key": None,              "arabic": ["تشقق", "شقوق"],       "label": "cracks",                "sector": "SAFETY"},
]

# Minimum character length for an arabizi form to be included (avoids noise)
MIN_FORM_LEN = 3

# Forms that are too generic / collision-prone — skip them
BLOCKLIST = {
    "sin", "ma", "mi", "me", "mo", "mu", "si", "na", "ni", "no", "wa", "wi",
    "fi", "fa", "fe", "la", "le", "li", "al", "el", "il", "bi", "ba", "sa",
    "sh", "ta", "ti", "ha", "hi", "ra", "ri", "ka", "ki", "da", "di",
    "water", "fire", "rain", "road", "gas",
    # False positives confirmed by manual review of rbz-ar.txt arabic_pattern:
    # chukair/shocair = شقير (Lebanese surname — matches قير substring but NOT tar/asphalt)
    "chukair", "shocair",
    # 3oulame2 = علماء (scholars — ماء is substring of علماء but word means scholars not water)
    "3oulame2",
    # mittarrif = متمطر/متطرف ambiguous — not a clean rain form
    "mittarrif",
    # mjare7 = مجارح (wounds with 7=ح) — NOT sewage; sewage is مجاري
    "mjare7",
    # 3amouuud = heavily elongated عمود — normalise collapse makes it 3amouud; skip noise form
    "3amouuud",
}


def normalise(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z0-9]", "", token)
    token = re.sub(r"[0146]+$", "", token)
    token = re.sub(r"([a-z0-9])\1{3,}", r"\1\1", token)
    return token


def parse_rbz_ar(path: Path) -> list[tuple[str, str]]:
    """Parse rbz-ar.txt → list of (arabizi_form, arabic_word) tuples."""
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # Split on first whitespace; arabizi is left, Arabic is right
        parts = line.split(None, 1)
        if len(parts) == 2:
            arabizi, arabic = parts
            pairs.append((arabizi.strip(), arabic.strip()))
    return pairs


def load_vocab(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_vocab(vocab: dict, path: Path) -> None:
    path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_existing_variant_forms(vocab: dict) -> dict[str, set[str]]:
    """Return map of term_key → set of normalised variant_forms."""
    result: dict[str, set[str]] = {}
    for key, meta in vocab.get("term_metadata", {}).items():
        result[key] = {normalise(vf) for vf in meta.get("variant_forms", [])}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine rbz-ar.txt for civic Arabizi variants")
    parser.add_argument("--apply", action="store_true", help="Apply clean new forms to vocab")
    args = parser.parse_args()

    if not RBZ_AR_PATH.exists():
        raise FileNotFoundError(f"rbz-ar.txt not found at {RBZ_AR_PATH}")

    pairs = parse_rbz_ar(RBZ_AR_PATH)
    print(f"Loaded {len(pairs)} arabizi→arabic pairs from rbz-ar.txt")

    vocab = load_vocab(VOCAB_PATH)
    existing = collect_existing_variant_forms(vocab)
    current_version = vocab.get("version", "unknown")

    # Build a fast lookup: arabic_word → [arabizi_forms]
    arabic_to_arabizi: dict[str, list[str]] = {}
    for arabizi, arabic in pairs:
        arabic_to_arabizi.setdefault(arabic, []).append(arabizi)

    # Mine each civic target
    report_rows: list[dict] = []
    patch_candidates: dict[str, list[str]] = {}  # vocab_key → new forms to add

    for target in CIVIC_TARGETS:
        key = target["key"]
        found_arabizi: list[str] = []

        for arabic_pattern in target["arabic"]:
            # Search by substring in arabic word
            for arabic_word, arabizi_forms in arabic_to_arabizi.items():
                if arabic_pattern in arabic_word:
                    for af in arabizi_forms:
                        norm = normalise(af)
                        if (
                            len(norm) >= MIN_FORM_LEN
                            and norm not in BLOCKLIST
                            and norm  # not empty after normalise
                        ):
                            found_arabizi.append(af)

        if not found_arabizi:
            continue

        deduped = sorted(set(found_arabizi))
        existing_forms = existing.get(key, set()) if key else set()
        new_forms = [f for f in deduped if normalise(f) not in existing_forms]
        already_covered = [f for f in deduped if normalise(f) in existing_forms]

        for form in deduped:
            report_rows.append({
                "vocab_key": key or "NEW_ENTRY",
                "sector": target["sector"],
                "label": target["label"],
                "arabizi_form": form,
                "normalised": normalise(form),
                "status": "ALREADY_COVERED" if normalise(form) in existing_forms else "NEW",
                "arabic_pattern": ",".join(target["arabic"]),
            })

        if new_forms and key:
            patch_candidates.setdefault(key, []).extend(new_forms)
            print(f"  {key:25s} {target['sector']:12s}  {len(new_forms):3d} new  {len(already_covered):3d} covered  | {new_forms[:5]}")
        elif new_forms:
            print(f"  {'NEW_ENTRY':25s} {target['sector']:12s}  {len(new_forms):3d} new (no vocab key yet) | {new_forms[:5]}")

    # Write report CSV
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["vocab_key", "sector", "label", "arabizi_form", "normalised", "status", "arabic_pattern"])
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"\nReport written → {REPORT_PATH.relative_to(ROOT)} ({len(report_rows)} rows)")

    total_new = sum(len(v) for v in patch_candidates.values())
    print(f"Total new forms across {len(patch_candidates)} vocab keys: {total_new}")

    if not args.apply:
        print("\n[DRY-RUN] Pass --apply to write changes to vocab.")
        return

    if current_version == NEW_VERSION:
        print(f"[SKIP] Vocab already at {NEW_VERSION}.")
        return

    if not patch_candidates:
        print("[INFO] No new forms to apply.")
        return

    # Apply patch
    backup_path = VOCAB_PATH.with_suffix(f".{NOW}.bak.json")
    shutil.copy2(VOCAB_PATH, backup_path)
    print(f"Backup: {backup_path.name}")

    term_meta = vocab.setdefault("term_metadata", {})
    applied_count = 0
    for key, new_forms in patch_candidates.items():
        if key not in term_meta:
            print(f"  [WARN] Key '{key}' not in term_metadata — skipping (need ADD not UPDATE)")
            continue
        existing_vf = set(term_meta[key].get("variant_forms", []))
        added = [f for f in new_forms if f not in existing_vf]
        if added:
            term_meta[key]["variant_forms"] = sorted(existing_vf | set(added))
            term_meta[key]["updated"] = NOW
            applied_count += len(added)
            print(f"  UPDATED {key}: +{len(added)} forms")

    entry = (
        f"{NEW_VERSION} ({NOW[:10]}): V19b rbz-ar civic mining — "
        f"{applied_count} new variant forms across {len(patch_candidates)} keys"
    )
    changelog = vocab.get("changelog", "")
    vocab["changelog"] = f"{entry}. {changelog}" if changelog else entry
    vocab["version"] = NEW_VERSION

    save_vocab(vocab, VOCAB_PATH)
    print(f"\n[OK] Saved vocab {NEW_VERSION} — {applied_count} forms added.")


if __name__ == "__main__":
    main()
