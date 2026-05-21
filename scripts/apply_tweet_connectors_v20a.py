#!/usr/bin/env python3
"""apply_tweet_connectors_v20a.py  —  V20a

Adds 13 Lebanese Arabizi connector / function-word groups to the vocab as
T3_GENERIC_SUPPORT entries.  All 21 variant forms were identified by mining
the 64,033-tweet lebanon.csv corpus and confirmed OOV against vocab v1.5.8.

Source script : scripts/mine_thesis_tweets_oov.py
Evidence file : data/knowledge_base/arabizi/lebanon_tweet_oov_candidates.csv

Run:
    python scripts/apply_tweet_connectors_v20a.py --dry-run
    python scripts/apply_tweet_connectors_v20a.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
NEW_VERSION = "1.6.0"

# ── V20a connector groups ─────────────────────────────────────────────────────
# Each tuple: (key, canonical, arabic, gloss, variant_forms)
# All 21 forms confirmed OOV vs v1.5.8 by mine_thesis_tweets_oov.py
V20A_GROUPS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "ana_pronoun",
        "ana",
        "أنا",
        "Lebanese Arabizi: 'I/me' (first-person pronoun). "
        "Connector/filler in civic tweet reports.",
        ["ana"],
    ),
    (
        "bas_connector",
        "bas",
        "بس",
        "Lebanese Arabizi: 'just/only/enough' (discourse particle). "
        "Single-s variant of 'bass' already in STOPWORDS.",
        ["bas"],
    ),
    (
        "eno_connector",
        "eno",
        "إنو",
        "Lebanese Arabizi: 'that/that-it' (subordinating conjunction). "
        "Variants enno/inno are phonological spelling differences.",
        ["eno", "enno", "inno"],
    ),
    (
        "hek_demonstrative",
        "hek",
        "هيك",
        "Lebanese Arabizi: 'like this / so / in this way' (demonstrative). "
        "High civic co-occurrence — used to describe road/infrastructure state.",
        ["hek"],
    ),
    (
        "hal_demonstrative",
        "hal",
        "هل",
        "Lebanese Arabizi: 'this / the' (determinative article/prefix before nouns). "
        "Very high frequency in civic descriptive sentences.",
        ["hal"],
    ),
    (
        "hada_demonstrative",
        "hada",
        "هاد",
        "Lebanese Arabizi: 'this / someone' (proximal demonstrative pronoun). "
        "Appears in civic descriptions: 'hada l-maw2if' = 'this situation'.",
        ["hada"],
    ),
    (
        "chou_question",
        "chou",
        "شو",
        "Lebanese Arabizi: 'what' (interrogative). "
        "Variant shu shares the same root; both OOV vs current vocab.",
        ["chou", "shu"],
    ),
    (
        "kif_question",
        "kif",
        "كيف",
        "Lebanese Arabizi: 'how' (interrogative). "
        "Frequent in civic complaints: 'kif badna n3ish' = 'how are we to live'.",
        ["kif"],
    ),
    (
        "eza_conditional",
        "eza",
        "إذا",
        "Lebanese Arabizi: 'if' (conditional conjunction). "
        "Variants eza/iza both confirmed OOV with civic_ratio ~0.87.",
        ["eza", "iza"],
    ),
    (
        "chi_indefinite",
        "chi",
        "شي",
        "Lebanese Arabizi: 'thing/something' (indefinite pronoun). "
        "Note: 'shi' is already in STOPWORDS; 'chi' is the French-influenced spelling.",
        ["chi"],
    ),
    (
        "ma3_preposition",
        "ma3",
        "مع",
        "Lebanese Arabizi: 'with' (preposition). "
        "Civic use: 'ma3 kell hayde' = 'with all this'. civic_ratio=0.867.",
        ["ma3"],
    ),
    (
        "hala2_temporal",
        "hala2",
        "هلق",
        "Lebanese Arabizi: 'now' (temporal marker). "
        "Used in civic urgency statements. Arabizi digit '2' = ء/glottal stop.",
        ["hala2"],
    ),
    (
        "ba2a_discourse",
        "ba2a",
        "بقى",
        "Lebanese Arabizi: 'then/so/already' (discourse marker). "
        "civic_ratio=0.60; used in complaint conclusions. '2' = glottal stop.",
        ["ba2a"],
    ),
]


def build_entry(
    key: str,
    canonical: str,
    arabic: str,
    gloss: str,
    forms: list[str],
    today: str,
) -> dict:
    return {
        "canonical_form": canonical,
        "arabic_equivalent": arabic,
        "semantic_type": "T3_GENERIC_SUPPORT",
        "sector_relevance": ["GENERAL"],
        "severity_relevance": ["LOW"],
        "false_friend_risk": "false",
        "must_not_auto_promote": "false",
        "loanword_from": None,
        "variant_forms": forms,
        "reviewer_id": "SYSTEM-V20a",
        "review_date": today,
        "confidence": "HIGH",
        "notes": gloss,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print plan; do not write.")
    args = ap.parse_args()

    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    current_version = vocab.get("version", "")
    if current_version == NEW_VERSION:
        print(f"[SKIP] vocab already at {NEW_VERSION}")
        return

    term_meta: dict = vocab.setdefault("term_metadata", {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_keys: list[str] = []
    updated_keys: list[str] = []
    total_forms = 0

    for key, canonical, arabic, gloss, forms in V20A_GROUPS:
        if key in term_meta:
            existing = set(term_meta[key].get("variant_forms", []))
            new_forms = [f for f in forms if f not in existing]
            if new_forms:
                term_meta[key]["variant_forms"] = sorted(existing | set(forms))
                updated_keys.append(key)
                total_forms += len(new_forms)
                if args.dry_run:
                    print(f"  [UPDATE] {key}: +{new_forms}")
        else:
            entry = build_entry(key, canonical, arabic, gloss, forms, today)
            term_meta[key] = entry
            new_keys.append(key)
            total_forms += len(forms)
            if args.dry_run:
                print(f"  [NEW]    {key}: {forms}")

    print(
        f"\n{'[DRY-RUN] ' if args.dry_run else ''}V20a plan: "
        f"{len(new_keys)} new groups, {len(updated_keys)} updated, "
        f"{total_forms} variant forms total"
    )

    if args.dry_run:
        print(f"\nNew groups    : {new_keys}")
        print(f"Updated groups: {updated_keys}")
        return

    # ── Backup ────────────────────────────────────────────────────────────────
    NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = VOCAB_PATH.with_suffix(f".{NOW}.bak.json")
    shutil.copy2(VOCAB_PATH, backup)
    print(f"[backup] {backup.name}")

    # ── Update version + changelog ────────────────────────────────────────────
    old_version = current_version
    vocab["version"] = NEW_VERSION
    changelog_entry = (
        f"{NEW_VERSION} ({today}): V20a tweet-corpus connector absorption — "
        f"{len(new_keys)} new groups, {total_forms} forms from lebanon.csv mining."
    )
    existing_log = vocab.get("changelog", "")
    vocab["changelog"] = (
        changelog_entry + (" | " + existing_log if existing_log else "")
    )

    VOCAB_PATH.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[OK] Saved vocab {NEW_VERSION} (was {old_version}) — "
        f"{len(new_keys)} new groups, {total_forms} forms."
    )


if __name__ == "__main__":
    main()
