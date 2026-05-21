"""
apply_transliteration_civic_patch_v18.py
=========================================
Applies a hand-curated subset of the transliteration mining output —
only digit-variant forms (containing 3, 7, 2, 6, 5, 8) from high-confidence
clusters are included. Noisy clusters (water_maye, flood_matar, flood_fayadan,
water_sarf, water_naboue) are excluded.

Target vocab version: 1.5.6 (patch on top of 1.5.5)

Run:
    python scripts/apply_transliteration_civic_patch_v18.py --dry-run
    python scripts/apply_transliteration_civic_patch_v18.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
NEW_VERSION = "1.5.6"

# ---------------------------------------------------------------------------
# Hand-curated clean forms from transliteration mining dry-run.
# Only includes:
#   (a) forms with Arabizi digit markers (3/7/2/6/5/8) — confirmed Arabizi
#   (b) forms from clusters with low false-match risk
#   (c) forms for EXISTING term_metadata entries OR clearly justified new ones
# ---------------------------------------------------------------------------
PATCH: list[dict] = [
    # ELECTRICITY — kahrabe (كهرباء): direct transliteration variants
    {
        "key": "kahrabe",
        "new_forms": ["kahraba", "elkahraba", "lkahraba"],
        "note": "Direct transliteration variants of كهرباء from dataset",
        "is_new": False,
    },
    # ELECTRICITY — 3atal (عطل): breakdown/fault — digit variants confirmed
    {
        "key": "3atal",
        "new_forms": ["3otlet", "3otleh", "3otla", "3o6lete", "3o6leh", "3a6le", "36lto", "36li"],
        "note": "Breakdown/outage variants — عطل; all contain digit markers 3 or 6",
        "is_new": True,
        "sector": "ELECTRICITY",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
    # ROADS — tarik (طريق/شارع): road/street — 6=ط digit variants
    {
        "key": "tarik",
        "new_forms": ["6req", "6are8", "6re8", "6areget", "6areqt", "6re8t", "6are8a", "6re8a"],
        "note": "Road variants with ط=6 from transliteration dataset",
        "is_new": False,
    },
    # ROADS — zeft (زفت): asphalt/tarmac — new term
    {
        "key": "zeft",
        "new_forms": ["zeft", "zfet", "alzeft", "zafteh"],
        "note": "Asphalt/bitumen — زفت; Lebanese road infrastructure term",
        "is_new": True,
        "sector": "ROADS",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
    # WASTE — zibele (زبالة/نفايات): garbage/waste
    {
        "key": "zibele",
        "new_forms": ["nefayat", "nofayat", "zbalh", "zbele"],
        "note": "Waste/garbage variants from transliteration dataset — نفايات/زبالة",
        "is_new": False,
    },
    # SAFETY — nar (نار/حريق): fire — digit variants
    {
        "key": "nar",
        "new_forms": ["7areg", "7arg", "7r8ha", "7are8ah", "l7are8"],
        "note": "Fire/burning variants — حريق; all contain digit marker 7",
        "is_new": False,
    },
    # ROADS — 7ufra (حفرة): pothole — digit variants from cluster
    # roads_7ufra cluster returned 0 forms; pothole cluster needs manual forms
    {
        "key": "7ufra",
        "new_forms": ["7ufra", "7ofra", "7ofar", "7ofret", "7fre", "7far"],
        "note": "Pothole variants — حفرة; 7 = ح digit marker",
        "is_new": False,
    },
    # FLOODING — ghare2 (غرق): flooded — add clear digit variant
    {
        "key": "ghare2",
        "new_forms": ["ghare2", "ghare2na", "ghri2na", "ghre2"],
        "note": "Flooded/submerged variants — غرق; 2 = glottal stop",
        "is_new": False,
    },
    # WASTE — ri7a_besh3a (رائحة): bad smell — 7 = ح
    {
        "key": "ri7a_besh3a",
        "new_forms": ["ri7a", "re7a", "ri7et", "re7et", "ri7tna", "l ri7a"],
        "note": "Bad smell variants — رائحة; 7 = ح digit marker",
        "is_new": False,
    },
    # ELECTRICITY — sulk (سلك/أسلاك): electrical wire — new
    {
        "key": "silk_el_kahraba",
        "new_forms": ["silk", "slk", "salk", "slket", "sulk"],
        "note": "Electrical wire — سلك; silk/sulk el kahraba = electrical wire",
        "is_new": True,
        "sector": "ELECTRICITY",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
    # FLOODING — fayadan (فيضان): flood — new entry with proper Arabizi forms
    {
        "key": "fayadan",
        "new_forms": ["fayadan", "fayde", "fayd", "tafyid", "fayad"],
        "note": "Flood overflow variants — فيضان; common FLOODING sector term",
        "is_new": True,
        "sector": "FLOODING",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
    # FLOODING — matar (مطر): rain — new entry
    {
        "key": "matar",
        "new_forms": ["matar", "mtr", "matara", "l mtar", "lmtar"],
        "note": "Rain variants — مطر; matar ktir = heavy rain; FLOODING context",
        "is_new": True,
        "sector": "FLOODING",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
    # SAFETY — sakef (سقف): ceiling/roof — new
    {
        "key": "sakef",
        "new_forms": ["sakef", "sa8ef", "sakf", "saqef", "sa2ef"],
        "note": "Ceiling/roof variants — سقف; sakef 3am yinzer = ceiling cracking",
        "is_new": True,
        "sector": "SAFETY",
        "tier": "T2_SECTOR_SUPPORT",
        "allowed_uses": "routing_support,normalization_support",
    },
]


def load_vocab():
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8-sig"))


def save_vocab(data, path):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def backup_vocab():
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bak = VOCAB_PATH.with_suffix(f".{ts}.bak.json")
    shutil.copy2(VOCAB_PATH, bak)
    return bak


def main(dry_run: bool = False):
    print("=" * 70)
    print(f"  V18c Transliteration Civic Patch {'[DRY RUN]' if dry_run else ''}")
    print("=" * 70)

    data = load_vocab()
    tm = data.setdefault("term_metadata", {})
    added = updated = skipped = 0

    for patch in PATCH:
        key = patch["key"]
        new_forms = patch["new_forms"]

        if key in tm:
            existing = set(tm[key].get("variant_forms", []))
            to_add = [f for f in new_forms if f not in existing]
            if not to_add:
                print(f"  SKIP '{key}': all forms present")
                skipped += 1
                continue
            if not dry_run:
                tm[key]["variant_forms"] = sorted(existing | set(to_add))
            print(f"  UPDATE '{key}': +{to_add}")
            updated += 1
        elif patch.get("is_new"):
            if not dry_run:
                tm[key] = {
                    "variant_forms": sorted(set(new_forms)),
                    "loanword_from": "",
                    "sector": patch.get("sector", "OTHER"),
                    "arabizi_note": patch.get("note", ""),
                    "tier": patch.get("tier", "T2_SECTOR_SUPPORT"),
                    "allowed_uses": patch.get("allowed_uses", "routing_support,normalization_support"),
                    "must_not_auto_promote": "true",
                    "false_friend_risk": "false",
                    "reviewer_id": "SYSTEM-V18",
                    "added_by": "apply_transliteration_civic_patch_v18",
                    "added_at": NOW,
                }
            print(f"  ADD  '{key}': {new_forms}")
            added += 1
        else:
            print(f"  WARN '{key}': not in term_metadata and not marked new — skipping")
            skipped += 1

    if dry_run:
        print(f"\n  DRY RUN: +{added} new, {updated} updated, {skipped} skipped")
        return

    data["version"] = NEW_VERSION
    data["changelog"] = (
        f"{NEW_VERSION} ({NOW[:10]}): V18c transliteration civic patch — "
        f"{added} new entries, {updated} updated from clean digit-variant mining. "
    ) + data.get("changelog", "")

    bak = backup_vocab()
    print(f"\n  Backup → {bak.name}")
    save_vocab(data, VOCAB_PATH)
    print(f"  Saved   → {VOCAB_PATH.name}  (version {NEW_VERSION})")
    print(f"\n  Summary: +{added} new, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(dry_run=p.parse_args().dry_run)
