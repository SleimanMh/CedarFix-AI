#!/usr/bin/env python3
"""Rank water page-inventory candidates for promotion or later review."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
WATER = ROOT / "data" / "knowledge_base" / "water_establishments"
INVENTORY = WATER / "page_inventory.csv"
SOURCE_REGISTRY = WATER / "source_registry.csv"
OUT = WATER / "source_candidate_review.csv"
TODAY = date.today().isoformat()

PROMOTE_KINDS = {
    "contact",
    "customer_service",
    "billing_or_payment",
    "water_quality",
    "projects_or_irrigation",
    "coverage_or_branch",
    "legal_or_mandate",
    "complaint_or_ticket",
}

NOISE_RE = re.compile(
    r"career|bids?|terms|gallery|prices?|ministers?|petroleum|electricity production|saving-energy|"
    r"timeline|register-business|news$|procurements?|photo|quick links|world bank|iva|BASILIS|"
    r"cooperation agreements|annual reports?|circulars?|external communications?|home page|"
    r"مناقصة|السيرة|وزير|البترول|النفط|الكهرباء|الكهربائي|الغاز|حفظ الطاقة|الأسعار|المعارض|اخبار",
    re.I,
)

WATER_SIGNAL_RE = re.compile(
    r"water|hydraulic|well|groundwater|dam|litani|qasim|ras al ain|pollution|quality|basin|"
    r"مياه|مائية|الابار|آبار|الليطاني|القاسمية|رأس العين|تلوث|السدود|الموارد المائية",
    re.I,
)

GENERIC_FORM_FIELD_RE = re.compile(
    r"globalsearch|searchtext|search\.\.\.|hidden|button|hoveredimage|href$|dxdate|orders?$",
    re.I,
)

STRONG_PROJECT_RE = re.compile(
    r"depollution|pollution|geomap|indicatorswater|waterquality|waterquantity|lraproject|"
    r"\bdam\b|basin|wells?|irrigation|qasim|ras al ain|projects\?l=3|"
    r"تلوث|خرائط|السدود|الابار|آبار|الموارد المائية|القاسمية|الري",
    re.I,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    headers = [
        "review_id",
        "entity_id",
        "action",
        "rank_score",
        "reason",
        "candidate_source_id",
        "existing_source_match",
        "page_kind",
        "title",
        "url",
        "phone_candidates",
        "email_candidates",
        "form_fields",
        "last_checked",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query_pairs = []
    seen_lang = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_") or low in {"fbclid", "gclid"}:
            continue
        if low == "lang":
            if seen_lang:
                continue
            seen_lang = True
        query_pairs.append((key, value))
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path or "/",
            "",
            urlencode(query_pairs, doseq=True),
            "",
        )
    )


def existing_source_urls() -> dict[str, str]:
    out: dict[str, str] = {}
    for row in read_csv(SOURCE_REGISTRY):
        url = row.get("url", "").strip()
        source_id = row.get("source_id", "").strip()
        if url and source_id:
            out[canonical_url(url)] = source_id
    return out


def has_meaningful_form_fields(value: str) -> bool:
    for field in [part.strip() for part in value.split(";") if part.strip()]:
        if not GENERIC_FORM_FIELD_RE.search(field):
            return True
    return False


def score_row(row: dict[str, str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    parsed = urlparse(row.get("url", ""))
    text = " ".join([row.get("title", ""), parsed.path, parsed.query, row.get("page_kind", "")])
    page_kind = row.get("page_kind", "")

    if page_kind in PROMOTE_KINDS:
        score += 45
        reasons.append(f"kind={page_kind}")
    if has_meaningful_form_fields(row.get("form_fields", "")):
        score += 20
        reasons.append("has_meaningful_form_fields")
    if row.get("phone_candidates", "") and page_kind in {"contact", "customer_service", "coverage_or_branch", "billing_or_payment", "complaint_or_ticket"}:
        score += 10
        reasons.append("has_contextual_phone")
    if row.get("email_candidates", ""):
        score += 10
        reasons.append("has_email")
    if WATER_SIGNAL_RE.search(text):
        score += 15
        reasons.append("water_signal")
    if NOISE_RE.search(text):
        score -= 45
        reasons.append("noise_keyword")
    if row.get("notes", "").startswith("fetch_error"):
        score -= 60
        reasons.append("fetch_error")
    if "cdn-cgi" in row.get("url", ""):
        score -= 80
        reasons.append("technical_page")
    return score, reasons


def has_strong_promotion_signal(row: dict[str, str]) -> bool:
    page_kind = row.get("page_kind", "")
    if page_kind in {"contact", "customer_service", "billing_or_payment", "coverage_or_branch", "legal_or_mandate", "complaint_or_ticket"}:
        return True
    if page_kind in {"water_quality"}:
        return True
    if page_kind == "projects_or_irrigation":
        return bool(STRONG_PROJECT_RE.search(" ".join([row.get("title", ""), row.get("url", "")])))
    return False


def choose_action(row: dict[str, str], score: int, duplicate: bool, existing_match: str) -> str:
    if existing_match:
        return "already_registered"
    if duplicate:
        return "duplicate_variant"
    if row.get("notes", "").startswith("fetch_error"):
        return "manual_retry_fetch"
    if score >= 70 and not has_strong_promotion_signal(row):
        return "review_later"
    if score >= 70:
        return "promote_candidate"
    if score >= 35:
        return "review_later"
    return "ignore_low_signal"


def main() -> int:
    inventory = read_csv(INVENTORY)
    sources_by_url = existing_source_urls()

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in inventory:
        grouped[(row.get("entity_id", ""), canonical_url(row.get("url", "")))].append(row)

    rows: list[dict[str, str]] = []
    for group_rows in grouped.values():
        group_rows.sort(key=lambda row: (row.get("source_status") != "existing_source", row.get("url", "")))
        representative_url = canonical_url(group_rows[0].get("url", ""))
        existing_match = sources_by_url.get(representative_url, "")

        for index, row in enumerate(group_rows):
            score, reasons = score_row(row)
            action = choose_action(row, score, duplicate=index > 0, existing_match=existing_match)
            rows.append(
                {
                    "review_id": "",
                    "entity_id": row.get("entity_id", ""),
                    "action": action,
                    "rank_score": str(score),
                    "reason": ";".join(reasons),
                    "candidate_source_id": row.get("candidate_source_id", ""),
                    "existing_source_match": existing_match,
                    "page_kind": row.get("page_kind", ""),
                    "title": row.get("title", ""),
                    "url": row.get("url", ""),
                    "phone_candidates": row.get("phone_candidates", ""),
                    "email_candidates": row.get("email_candidates", ""),
                    "form_fields": row.get("form_fields", ""),
                    "last_checked": row.get("last_checked", TODAY),
                    "notes": row.get("notes", ""),
                }
            )

    rows.sort(key=lambda row: (row["action"] != "promote_candidate", -int(row["rank_score"]), row["entity_id"], row["url"]))
    for index, row in enumerate(rows, start=1):
        row["review_id"] = f"WSCR-{index:04d}"

    write_csv(OUT, rows)
    counts = defaultdict(int)
    for row in rows:
        counts[row["action"]] += 1
    print(f"Wrote {len(rows)} review rows to {OUT.relative_to(ROOT)}")
    for action in sorted(counts):
        print(f"{action}: {counts[action]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
