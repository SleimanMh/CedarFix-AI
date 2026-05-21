#!/usr/bin/env python3
"""mine_thesis_tweets_oov.py  —  V20 prep

Mines all 64,033 Lebanese tweets from the thesis dataset for OOV Arabizi
tokens not yet covered by the vocabulary, then ranks them by a composite
frequency × civic-proximity score for human review.

Source : data/external_sources/manual_drop/thesis_extracted/
             thesis/Misc/Tweets/lebanon.csv
Output : data/knowledge_base/arabizi/lebanon_tweet_oov_candidates.csv

Usage:
    python scripts/mine_thesis_tweets_oov.py             # default: min-freq 3
    python scripts/mine_thesis_tweets_oov.py --min-freq 5
    python scripts/mine_thesis_tweets_oov.py --top 50    # narrower console view

Score formula:
    score = freq × (1 + 2·civic_ratio + 0.5·arabizi_ctx_ratio)
    - civic_ratio        : fraction of occurrences co-located with a known civic token
    - arabizi_ctx_ratio  : fraction of occurrences in tweets that also contain an
                           Arabizi-digit token (catches digit-free Arabizi like "wein")
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
TWEET_CSV = (
    ROOT
    / "data"
    / "external_sources"
    / "manual_drop"
    / "thesis_extracted"
    / "thesis"
    / "Misc"
    / "Tweets"
    / "lebanon.csv"
)
OUT_CSV = ROOT / "data" / "knowledge_base" / "arabizi" / "lebanon_tweet_oov_candidates.csv"

TWEET_COL = 1  # 0-indexed; CSV has no header row

# ── Replication of arabizi_features normalisation (must be byte-for-byte identical) ──
TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
ARABIZI_DIGIT_RE = re.compile(r"[235789]")
HIGH_RISK_RE = re.compile(r"(5tr|5atr|5atar|khatar|m5atr|sa32|saa2|ghaz|7ar2|7are2)", re.I)

# Pure-noise patterns to skip even when freq qualifies
SKIP_PATTERNS = re.compile(
    r"^(https?|www|http|com|org|net|co|rt|via|amp|gt|lt|nbsp)$", re.I
)


def normalise_token(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z0-9]", "", token)
    token = re.sub(r"[0146]+$", "", token)
    token = re.sub(r"([a-z0-9])\1{3,}", r"\1\1", token)
    return token


def tokenize(text: str) -> list[str]:
    return [n for t in TOKEN_RE.findall(text) if (n := normalise_token(t))]


def iter_strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for i in v:
            yield from iter_strings(i)
    elif isinstance(v, dict):
        for i in v.values():
            yield from iter_strings(i)


def build_known_and_civic(
    vocab: dict,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Returns (known_tokens, civic_tokens, HIGH_RISK_HINTS) matching
    the exact logic of load_vocabulary_index in arabizi_features.py."""
    from src.shared.arabizi_lexical_policy import (
        HIGH_RISK_HINTS,
        IGNORED_OOV_TOKENS,
        STOPWORDS,
    )

    known: set[str] = set(STOPWORDS) | set(IGNORED_OOV_TOKENS)
    civic: set[str] = set()

    for text in iter_strings(vocab.get("arabizi_notes", {})):
        known.update(tokenize(text))

    for sector in vocab.get("sectors", {}).values():
        for seeds in sector.get("issue_type_keywords", {}).values():
            for seed in iter_strings(seeds):
                toks = tokenize(seed)
                known.update(toks)
                civic.update(toks)
        for section in ("sample_complaints", "catch_all_phrases", "issue_type_aliases"):
            for text in iter_strings(sector.get(section, {})):
                toks = tokenize(text)
                known.update(toks)
                civic.update(toks)

    for metadata in vocab.get("term_metadata", {}).values():
        for variant in metadata.get("variant_forms", []):
            nt = normalise_token(variant)
            if nt:
                known.add(nt)
                civic.add(nt)  # all domain vocab is civic by definition

    return (
        frozenset(t for t in known if t),
        frozenset(t for t in civic if t),
        HIGH_RISK_HINTS,
    )


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Mine OOV Arabizi tokens from 64K Lebanese tweets.")
    ap.add_argument(
        "--min-freq",
        type=int,
        default=3,
        metavar="N",
        help="Min total occurrences to include a token (default: 3)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=200,
        metavar="N",
        help="How many rows to print to console (default: 200)",
    )
    args = ap.parse_args()

    # ── 1. Load vocabulary ────────────────────────────────────────────────────
    print("[1/5] Loading vocabulary …")
    if not VOCAB_PATH.exists():
        sys.exit(f"[ERROR] vocab not found: {VOCAB_PATH}")
    vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    known_tokens, civic_tokens, HIGH_RISK = build_known_and_civic(vocab)
    print(
        f"      vocab v{vocab.get('version', '?')}  |  "
        f"known_tokens={len(known_tokens):,}  civic_tokens={len(civic_tokens):,}"
    )

    # ── 2. Read tweets ────────────────────────────────────────────────────────
    print("[2/5] Reading tweets …")
    if not TWEET_CSV.exists():
        sys.exit(f"[ERROR] Tweet CSV not found: {TWEET_CSV}")

    tweet_texts: list[str] = []
    with open(TWEET_CSV, encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) > TWEET_COL:
                text = row[TWEET_COL].strip()
                if text:
                    tweet_texts.append(text)
    print(f"      {len(tweet_texts):,} tweet rows loaded")

    # ── 3. Tokenise & collect counts ──────────────────────────────────────────
    print("[3/5] Tokenising all tweets …")

    oov_freq: dict[str, int] = defaultdict(int)
    oov_distinct: dict[str, int] = defaultdict(int)
    oov_civic: dict[str, int] = defaultdict(int)
    oov_az_ctx: dict[str, int] = defaultdict(int)
    oov_raw: dict[str, Counter] = defaultdict(Counter)
    oov_sample: dict[str, str] = {}

    for tweet_text in tweet_texts:
        raw_tokens = TOKEN_RE.findall(tweet_text)
        norm_tokens = [normalise_token(t) for t in raw_tokens]

        # Tweet-level flags (computed once per tweet)
        tweet_has_civic = any(nt in civic_tokens for nt in norm_tokens if nt)
        tweet_has_az_digit = any(ARABIZI_DIGIT_RE.search(rt) for rt in raw_tokens)

        seen: set[str] = set()
        for raw, norm in zip(raw_tokens, norm_tokens):
            if not norm or len(norm) < 3:
                continue
            if norm in known_tokens:
                continue
            if norm.isdigit():
                continue
            if SKIP_PATTERNS.match(norm):
                continue

            oov_freq[norm] += 1
            oov_raw[norm][raw.lower()] += 1

            if norm not in seen:
                oov_distinct[norm] += 1
                seen.add(norm)
                if tweet_has_civic:
                    oov_civic[norm] += 1
                if tweet_has_az_digit:
                    oov_az_ctx[norm] += 1
                if norm not in oov_sample:
                    oov_sample[norm] = tweet_text[:120]

    raw_oov_count = len(oov_freq)
    print(f"      {raw_oov_count:,} unique OOV types (before filters)")

    # ── 4. Filter & score ─────────────────────────────────────────────────────
    print("[4/5] Filtering & scoring …")

    rows: list[dict] = []
    for norm, freq in oov_freq.items():
        if freq < args.min_freq:
            continue

        distinct = oov_distinct[norm]
        civic_co = oov_civic.get(norm, 0)
        az_ctx = oov_az_ctx.get(norm, 0)
        civic_ratio = civic_co / distinct if distinct else 0.0
        az_ctx_ratio = az_ctx / distinct if distinct else 0.0

        has_az_digit = int(any(ARABIZI_DIGIT_RE.search(r) for r in oov_raw[norm]))

        # Interest gate: must be Arabizi-digit, Arabizi-context, OR civic-adjacent
        # Pure-Latin tokens with zero signal in all three dimensions are discarded.
        if has_az_digit == 0 and az_ctx_ratio == 0.0 and civic_ratio == 0.0:
            continue

        # Composite score: frequency × context multiplier
        score = freq * (1.0 + 2.0 * civic_ratio + 0.5 * az_ctx_ratio)

        guardrailed = int(norm in HIGH_RISK or bool(HIGH_RISK_RE.search(norm)))

        top_raw = "|".join(
            f"{form}({cnt})" for form, cnt in oov_raw[norm].most_common(5)
        )
        sample = oov_sample.get(norm, "")[:100]

        rows.append(
            {
                "normalised_token": norm,
                "top_raw_forms": top_raw,
                "freq": freq,
                "distinct_tweets": distinct,
                "civic_co_occ": civic_co,
                "civic_ratio": f"{civic_ratio:.3f}",
                "az_ctx_count": az_ctx,
                "az_ctx_ratio": f"{az_ctx_ratio:.3f}",
                "score": f"{score:.1f}",
                "has_arabizi_digit": has_az_digit,
                "guardrailed": guardrailed,
                "sample_tweet": sample,
            }
        )

    rows.sort(key=lambda r: float(r["score"]), reverse=True)
    print(f"      {len(rows):,} candidates after filtering (min_freq={args.min_freq})")

    # ── 5. Write CSV ──────────────────────────────────────────────────────────
    print("[5/5] Writing output …")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "normalised_token",
        "top_raw_forms",
        "freq",
        "distinct_tweets",
        "civic_co_occ",
        "civic_ratio",
        "az_ctx_count",
        "az_ctx_ratio",
        "score",
        "has_arabizi_digit",
        "guardrailed",
        "sample_tweet",
    ]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"      Written → {OUT_CSV.name}")
    print()

    # ── Console summary ───────────────────────────────────────────────────────
    az_count = sum(1 for r in rows if r["has_arabizi_digit"])
    guard_count = sum(1 for r in rows if r["guardrailed"])
    civic_only = sum(1 for r in rows if not r["has_arabizi_digit"] and float(r["civic_ratio"]) > 0)

    print("═" * 90)
    print("  SUMMARY")
    print("═" * 90)
    print(f"  Total tweets processed   : {len(tweet_texts):,}")
    print(f"  Raw OOV types found      : {raw_oov_count:,}")
    print(f"  Candidates (freq≥{args.min_freq})     : {len(rows):,}")
    print(f"  ├─ With Arabizi digit    : {az_count:,}")
    print(f"  ├─ Civic-adjacent only   : {civic_only:,}")
    print(f"  └─ Guardrailed           : {guard_count:,}")
    print()

    top_display = rows[: args.top]
    print(f"TOP {min(args.top, len(rows))} CANDIDATES  (sorted by score desc)")
    print(
        f"  {'Token':<22} {'Freq':>6} {'CivCo':>6} {'CivR':>6} {'AzCtxR':>7} "
        f"{'Score':>8}  Az  G  Top raw forms"
    )
    print("  " + "─" * 90)
    for r in top_display:
        az = "✓" if r["has_arabizi_digit"] else " "
        gr = "⚠" if r["guardrailed"] else " "
        print(
            f"  {r['normalised_token']:<22} {r['freq']:>6} {r['civic_co_occ']:>6} "
            f"{r['civic_ratio']:>6} {r['az_ctx_ratio']:>7} {r['score']:>8}"
            f"  {az}   {gr}  {r['top_raw_forms'][:45]}"
        )

    print()
    print(f"[OK] Full results → {OUT_CSV}")


if __name__ == "__main__":
    main()
