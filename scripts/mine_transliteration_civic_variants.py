"""
mine_transliteration_civic_variants.py
=======================================
Mines the Arabizi Transliteration Dataset (21,499 Arabize↔Arabic pairs) for
civic/infrastructure term variants and adds them to arabizi_vocabulary.json
term_metadata.

The dataset provides authoritative Arabizi→Arabic mappings, so any Arabic word
that maps to a civic root (water, electricity, roads, waste, flooding, safety)
gives us ground-truth Arabizi spelling variants.

Run:
    python scripts/mine_transliteration_civic_variants.py --dry-run
    python scripts/mine_transliteration_civic_variants.py
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
TRANSL_PATH = ROOT / "data" / "external_sources" / "manual_drop" / "Arabizi_Transliteration_Dataset" / "train.csv"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NEW_VERSION = "1.5.4"

# ---------------------------------------------------------------------------
# Arabic root clusters → sector mapping
# If an Arabic word CONTAINS any of these substrings, it belongs to that cluster
# ---------------------------------------------------------------------------
ARABIC_CIVIC_CLUSTERS: dict[str, dict] = {
    # WATER
    "water_maye": {
        "arabic_contains": ["ماء", "مياه", "مية", "ماي"],
        "sector": "WATER",
        "term_key": "mayye",
        "arabizi_note": "water — مياه/ماء variant from transliteration dataset",
    },
    "water_sarf": {
        "arabic_contains": ["صرف", "صرفية"],
        "sector": "WATER",
        "term_key": "sarf",
        "arabizi_note": "drainage/sewage — صرف; sarf el miye = water drainage",
    },
    "water_naboue": {
        "arabic_contains": ["نبوع", "نبع", "ينبوع"],
        "sector": "WATER",
        "term_key": "nab3",
        "arabizi_note": "spring/source — نبع; variant of nab3",
    },
    # ELECTRICITY
    "elec_kahraba": {
        "arabic_contains": ["كهرباء", "كهربا", "كهربة"],
        "sector": "ELECTRICITY",
        "term_key": "kahrabe",
        "arabizi_note": "electricity — كهرباء variant from transliteration dataset",
    },
    "elec_generator": {
        "arabic_contains": ["مولد", "جنراتور", "مولدة"],
        "sector": "ELECTRICITY",
        "term_key": "moulid",
        "arabizi_note": "generator — مولد variant from transliteration dataset",
    },
    "elec_sulk": {
        "arabic_contains": ["سلك", "أسلاك", "كابل"],
        "sector": "ELECTRICITY",
        "term_key": "silk_el_kahraba",
        "arabizi_note": "electrical wire/cable — سلك; sulk/silk kahraba",
        "new_entry": True,
    },
    "elec_3ata": {
        "arabic_contains": ["عطل", "أعطال", "عطلان"],
        "sector": "ELECTRICITY",
        "term_key": "3atal",
        "arabizi_note": "breakdown/outage — عطل; 3atal bil kahraba = electrical fault",
        "new_entry": True,
    },
    # ROADS
    "roads_tari2": {
        "arabic_contains": ["طريق", "طرقات", "شارع"],
        "sector": "ROADS",
        "term_key": "tarik",
        "arabizi_note": "road/street — طريق/شارع variant from transliteration dataset",
    },
    "roads_7ufra": {
        "arabic_contains": ["حفرة", "حفر", "حفرات"],
        "sector": "ROADS",
        "term_key": "7ufra",
        "arabizi_note": "pothole/hole — حفرة variant from transliteration dataset",
    },
    "roads_iskalt": {
        "arabic_contains": ["أسفلت", "إسفلت", "زفت"],
        "sector": "ROADS",
        "term_key": "zeft",
        "arabizi_note": "asphalt/tarmac — زفت/أسفلت; zeft = bitumen (Lebanese)",
        "new_entry": True,
    },
    "roads_balate": {
        "arabic_contains": ["بلاط", "بلاطة", "تبليط"],
        "sector": "ROADS",
        "term_key": "balate",
        "arabizi_note": "paving/tiles — بلاط; balate el share3 = road paving",
        "new_entry": True,
    },
    "roads_3ajale": {
        "arabic_contains": ["عجلة", "عجلات", "إطار"],
        "sector": "ROADS",
        "term_key": "3jelet",
        "arabizi_note": "wheel/tire — عجلة variant from transliteration dataset",
    },
    # WASTE
    "waste_zbale": {
        "arabic_contains": ["زبالة", "زبل", "قمامة", "نفايات"],
        "sector": "WASTE",
        "term_key": "zibele",
        "arabizi_note": "garbage/waste — زبالة variant from transliteration dataset",
    },
    "waste_7awiyet": {
        "arabic_contains": ["حاوية", "حاويات", "كونتينر"],
        "sector": "WASTE",
        "term_key": "7awiyet",
        "arabizi_note": "waste bin/dumpster — حاوية; 7awiyet el zbele = waste container",
        "new_entry": True,
    },
    "waste_ri7a": {
        "arabic_contains": ["رائحة", "ريحة", "نتن"],
        "sector": "WASTE",
        "term_key": "ri7a_besh3a",
        "arabizi_note": "bad smell — رائحة variant from transliteration dataset",
    },
    # FLOODING
    "flood_fayadan": {
        "arabic_contains": ["فيضان", "فاض", "طوفان"],
        "sector": "FLOODING",
        "term_key": "fayadan",
        "arabizi_note": "flood/overflow — فيضان",
        "new_entry": True,
    },
    "flood_matar": {
        "arabic_contains": ["مطر", "أمطار", "شتا"],
        "sector": "FLOODING",
        "term_key": "matar",
        "arabizi_note": "rain — مطر; matar ktir = heavy rain",
        "new_entry": True,
    },
    "flood_ghare2": {
        "arabic_contains": ["غرق", "غارق", "غرقان"],
        "sector": "FLOODING",
        "term_key": "ghare2",
        "arabizi_note": "flooded/sinking — غرق variant from transliteration dataset",
    },
    # SAFETY
    "safety_5atar": {
        "arabic_contains": ["خطر", "أخطار", "خطير"],
        "sector": "SAFETY",
        "term_key": "5atar",
        "arabizi_note": "danger — خطر; 5atar = danger (HIGH_RISK_HINTS list)",
    },
    "safety_7ari2a": {
        "arabic_contains": ["حريق", "حرق", "نار"],
        "sector": "SAFETY",
        "term_key": "nar",
        "arabizi_note": "fire — نار/حريق variant from transliteration dataset",
    },
    "safety_jdar": {
        "arabic_contains": ["جدار", "جدران", "حائط"],
        "sector": "SAFETY",
        "term_key": "7eet",
        "arabizi_note": "wall — حائط/جدار variant from transliteration dataset",
    },
    "safety_sakaf": {
        "arabic_contains": ["سقف", "أسقف", "سقوط"],
        "sector": "SAFETY",
        "term_key": "sakef",
        "arabizi_note": "ceiling/roof collapse — سقف; sakef 3am yinzer = ceiling about to fall",
        "new_entry": True,
    },
}

# Normalise for evaluator coverage (mirrors arabizi_features.py logic)
def normalise_token(tok: str) -> str:
    t = tok.lower()
    t = re.sub(r"[^a-z0-9]", "", t)
    t = re.sub(r"[0146]+$", "", t)
    t = re.sub(r"(.)\1{3,}", r"\1\1", t)
    return t


def load_vocab():
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8-sig"))


def save_vocab(data, path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def backup_vocab():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = VOCAB_PATH.with_suffix(f".{ts}.bak.json")
    shutil.copy2(VOCAB_PATH, bak)
    return bak


def mine_transliteration() -> dict[str, list[str]]:
    """
    Returns {term_key: [arabizi_forms...]} from the transliteration dataset.
    """
    if not TRANSL_PATH.exists():
        print(f"  WARN: transliteration dataset not found at {TRANSL_PATH}")
        return {}

    rows = list(csv.DictReader(TRANSL_PATH.open(encoding="utf-8-sig", errors="replace")))
    print(f"  Loaded {len(rows)} transliteration pairs")

    # Build: arabic_word → list[arabizi_form]
    arabic_to_arabizi: dict[str, list[str]] = {}
    for row in rows:
        ar = row.get("Arabic", "").strip()
        az = row.get("Arabize", "").strip()
        if ar and az and len(az) >= 2:
            arabic_to_arabizi.setdefault(ar, []).append(az.lower())

    # For each civic cluster, find matching Arabic words
    cluster_forms: dict[str, list[str]] = {}  # term_key → [arabizi...]
    for cluster_id, cluster in ARABIC_CIVIC_CLUSTERS.items():
        term_key = cluster["term_key"]
        found: list[str] = []
        for ar_word, az_forms in arabic_to_arabizi.items():
            if any(needle in ar_word for needle in cluster["arabic_contains"]):
                for az in az_forms:
                    norm = normalise_token(az)
                    if norm and norm not in found:
                        found.append(norm)
        if found:
            cluster_forms.setdefault(term_key, []).extend(found)
            print(f"  Cluster '{cluster_id}': {len(found)} new forms → {found[:5]}")

    # Deduplicate per term_key
    return {k: sorted(set(v)) for k, v in cluster_forms.items()}


def apply_to_vocab(mined: dict[str, list[str]], dry_run: bool) -> tuple[int, int, int]:
    data = load_vocab()
    tm = data.setdefault("term_metadata", {})
    added = updated = skipped = 0

    # Identify new entries needed (has new_entry: True in cluster config)
    new_entry_keys = {
        cl["term_key"]
        for cl in ARABIC_CIVIC_CLUSTERS.values()
        if cl.get("new_entry")
    }

    for term_key, new_forms in mined.items():
        if not new_forms:
            continue

        if term_key not in tm:
            if term_key in new_entry_keys:
                # Find the cluster note for this key
                notes = [
                    cl["arabizi_note"]
                    for cl in ARABIC_CIVIC_CLUSTERS.values()
                    if cl["term_key"] == term_key
                ]
                sectors = list({
                    cl["sector"]
                    for cl in ARABIC_CIVIC_CLUSTERS.values()
                    if cl["term_key"] == term_key
                })
                if not dry_run:
                    tm[term_key] = {
                        "variant_forms": new_forms,
                        "loanword_from": "",
                        "sector": ",".join(sectors),
                        "arabizi_note": notes[0] if notes else "",
                        "added_by": "mine_transliteration_civic_variants",
                        "added_at": NOW,
                    }
                print(f"  ADD  '{term_key}': {new_forms[:4]}")
                added += 1
            else:
                print(f"  SKIP '{term_key}': not in term_metadata and not marked new_entry")
                skipped += 1
            continue

        existing = set(tm[term_key].get("variant_forms", []))
        to_add = [f for f in new_forms if f not in existing]
        if not to_add:
            print(f"  SKIP '{term_key}': all {len(new_forms)} forms already present")
            skipped += 1
            continue

        if not dry_run:
            tm[term_key]["variant_forms"] = sorted(existing | set(to_add))
        print(f"  UPDATE '{term_key}': +{len(to_add)} forms → {to_add[:5]}")
        updated += 1

    if not dry_run:
        data["version"] = NEW_VERSION
        data["changelog"] = (
            f"{NEW_VERSION} ({NOW[:10]}): V18 transliteration civic mining — "
            f"{added} new, {updated} updated term_metadata entries from 21K Arabizi↔Arabic pairs. "
        ) + data.get("changelog", "")
        bak = backup_vocab()
        print(f"\n  Backup → {bak.name}")
        save_vocab(data, VOCAB_PATH)
        print(f"  Saved   → {VOCAB_PATH.name}  (version {NEW_VERSION})")

    return added, updated, skipped


def main(dry_run: bool = False):
    print("=" * 70)
    print(f"  V18 Transliteration Civic Variant Mining {'[DRY RUN]' if dry_run else ''}")
    print("=" * 70)

    mined = mine_transliteration()
    print()

    if not mined:
        print("  No civic forms mined from transliteration dataset. Nothing to do.")
        return

    added, updated, skipped = apply_to_vocab(mined, dry_run)
    print(f"\n  Summary: +{added} new entries, {updated} updated, {skipped} skipped")
    if not dry_run:
        print("\n  Run validators:")
        print("    python scripts/validate_arabizi_vocabulary.py")
        print("    python scripts/evaluate_arabizi_coverage.py")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(dry_run=p.parse_args().dry_run)
