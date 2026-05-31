#!/usr/bin/env python3
"""Inventory official water-establishment pages for CedarFix KB expansion.

The script crawls only a small allowlist of official/partner domains seeded from
data/knowledge_base/water_establishments/source_registry.csv. It writes data
artifacts under data/knowledge_base/water_establishments/ and keeps executable
logic in scripts/.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback for lean environments
    BeautifulSoup = None


ROOT = Path(__file__).resolve().parents[1]
WATER_DIR = ROOT / "data" / "knowledge_base" / "water_establishments"
SOURCE_REGISTRY = WATER_DIR / "source_registry.csv"
OUT_INVENTORY = WATER_DIR / "page_inventory.csv"
OUT_REPORT = WATER_DIR / "scrape_run_report.md"

USER_AGENT = "CedarFix water-establishment coverage audit/1.0 (+local research script)"
TODAY = date.today().isoformat()

ALLOWED_HOSTS = {
    "ebml.gov.lb",
    "eeln.gov.lb",
    "www.slwe.gov.lb",
    "slwe.gov.lb",
    "bwe.gov.lb",
    "www.energyandwater.gov.lb",
    "energyandwater.gov.lb",
    "www.litani.gov.lb",
    "litani.gov.lb",
    "www.omt.com.lb",
    "omt.com.lb",
}

NO_DEEP_CRAWL_HOSTS = {
    "www.omt.com.lb",
    "omt.com.lb",
}

ENTITY_BY_SOURCE_PREFIX = {
    "SRC-BMLWE-": "BMLWE",
    "SRC-NLWE-": "NLWE",
    "SRC-SLWE-": "SLWE",
    "SRC-BWE-": "BWE",
    "SRC-MEW-": "MEW",
    "SRC-MOEW-": "MEW",
    "SRC-LRA-": "LRA",
}

PAGE_KIND_PATTERNS = [
    ("complaint_or_ticket", r"complaint|ticket|شكوى|شكاوى|مراجعة"),
    ("contact", r"contact|اتصل|تواصل|phone|hotline|هاتف|خط ساخن"),
    ("customer_service", r"customer service|customer-services|خدمة الزبائن|مشترك|subscriber"),
    ("forms_or_documents", r"forms?|documents?|مستندات|معاملة|معاملات|طلب|طلبات"),
    ("billing_or_payment", r"bill|invoice|payment|pay|فاتورة|دفع|تسديد|قبض"),
    ("service_request", r"subscription|connection|transfer|cancel|suspend|اشتراك|نقل|الغاء|إلغاء"),
    ("water_quality", r"quality|laborator|chlorin|تلوث|نوعية|مختبر|كلور"),
    ("coverage_or_branch", r"branch|office|district|department|مركز|دائرة|فرع|توزيع"),
    ("legal_or_mandate", r"law|legal|decree|mandate|قانون|مرسوم|نظام"),
    ("projects_or_irrigation", r"irrigation|litani|qasm|ras al ain|ري|القاسمية|رأس العين|الليطاني"),
    ("about", r"about|mission|overview|نبذة|تعريف"),
    ("news_or_notice", r"news|notice|announcement|اعلان|أخبار|خبر"),
]

INTERESTING_KINDS = {
    "complaint_or_ticket",
    "contact",
    "customer_service",
    "forms_or_documents",
    "billing_or_payment",
    "service_request",
    "water_quality",
    "coverage_or_branch",
    "legal_or_mandate",
    "projects_or_irrigation",
}

PHONE_RE = re.compile(
    r"(?:(?:\+?961|0)\s*[-/]?\s*)?(?:1|3|4|5|6|7|8|9|70|71|76|78|79|81)\s*[-/]?\s*\d{3}\s*[-/]?\s*\d{3}|\b1[0-9]{3}\b"
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Seed:
    source_id: str
    entity_id: str
    url: str
    title: str
    publisher: str


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.form_fields: list[str] = []
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._in_title = False
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag == "title":
            self._in_title = True
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag in {"input", "select", "textarea"}:
            candidates = [
                attrs_dict.get("name", ""),
                attrs_dict.get("id", ""),
                attrs_dict.get("placeholder", ""),
                attrs_dict.get("aria-label", ""),
                attrs_dict.get("type", ""),
            ]
            clean = "|".join(item for item in candidates if item).strip()
            if clean:
                self.form_fields.append(clean)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if not data:
            return
        if self._in_title:
            self._title_parts.append(data)
        elif not self._skip:
            self._text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(self._title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def entity_for_source(source_id: str) -> str:
    for prefix, entity_id in ENTITY_BY_SOURCE_PREFIX.items():
        if source_id.startswith(prefix):
            return entity_id
    return "UNKNOWN"


def load_seeds() -> list[Seed]:
    seeds: list[Seed] = []
    for row in read_csv(SOURCE_REGISTRY):
        url = row.get("url", "").strip()
        if not url:
            continue
        host = urlparse(url).netloc.lower()
        if host not in ALLOWED_HOSTS:
            continue
        seeds.append(
            Seed(
                source_id=row.get("source_id", "").strip(),
                entity_id=entity_for_source(row.get("source_id", "")),
                url=url,
                title=row.get("title", "").strip(),
                publisher=row.get("publisher", "").strip(),
            )
        )
    return seeds


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        low = key.lower()
        if low.startswith("utm_") or low in {"fbclid", "gclid"}:
            continue
        query_items.append((key, value))
    query = urlencode(query_items, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    if host not in ALLOWED_HOSTS:
        return False
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".zip"]):
        return False
    return True


def parse_html(html: str) -> tuple[str, str, list[str], list[str]]:
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = soup.get_text(" ", strip=True)
        links = [a.get("href", "") for a in soup.find_all("a", href=True)]
        fields: list[str] = []
        for tag in soup.find_all(["input", "select", "textarea"]):
            values = [
                tag.get("name", ""),
                tag.get("id", ""),
                tag.get("placeholder", ""),
                tag.get("aria-label", ""),
                tag.get("type", ""),
            ]
            clean = "|".join(item for item in values if item).strip()
            if clean:
                fields.append(clean)
        return title, text, links, fields

    parser = LinkParser()
    parser.feed(html)
    return parser.title, parser.text, parser.links, parser.form_fields


def classify_page(url: str, title: str, text: str) -> tuple[str, list[str]]:
    primary = f"{url} {title}".lower()
    hits = [kind for kind, pattern in PAGE_KIND_PATTERNS if re.search(pattern, primary, re.I)]
    if hits:
        return hits[0], hits

    # Body text often includes shared footer/navigation words such as "contact"
    # or "claims", so only use it for high-signal domain concepts.
    body_patterns = [
        (kind, pattern)
        for kind, pattern in PAGE_KIND_PATTERNS
        if kind
        in {
            "water_quality",
            "projects_or_irrigation",
            "legal_or_mandate",
            "forms_or_documents",
            "service_request",
        }
    ]
    haystack = text[:5000].lower()
    hits = [kind for kind, pattern in body_patterns if re.search(pattern, haystack, re.I)]
    page_kind = hits[0] if hits else "general"
    return page_kind, hits


def language_hint(text: str) -> str:
    arabic_chars = sum(1 for char in text[:4000] if "\u0600" <= char <= "\u06ff")
    latin_chars = sum(1 for char in text[:4000] if ("a" <= char.lower() <= "z"))
    if arabic_chars and arabic_chars > latin_chars:
        return "ar"
    if latin_chars:
        return "en_or_latin"
    return "unknown"


def slug_for_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [item for item in parsed.path.strip("/").split("/") if item]
    if not parts:
        return "HOME"
    raw = "-".join(parts[-2:])
    raw = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").upper()
    return raw[:36] or "PAGE"


def source_status(url: str, page_kind: str, existing_urls: set[str]) -> tuple[str, str]:
    if canonicalize_url(url) in existing_urls:
        return "existing_source", "high"
    if page_kind in INTERESTING_KINDS:
        return "official_candidate", "medium"
    return "low_signal_official_page", "low"


def fetch_url(url: str, timeout: float) -> tuple[str, str, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = str(getattr(response, "status", ""))
            final_url = canonicalize_url(response.geturl())
            content_type = response.headers.get("content-type", "")
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
            return status_code, final_url, content_type, body
    except HTTPError as exc:
        raw = exc.read()
        body = raw.decode("utf-8", errors="replace") if raw else ""
        return str(exc.code), canonicalize_url(exc.geturl() or url), exc.headers.get("content-type", ""), body
    except TimeoutError as exc:
        raise RuntimeError("timeout") from exc
    except URLError as exc:
        raise RuntimeError(exc.reason) from exc


def compact(items: list[str], limit: int = 12) -> str:
    clean: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = re.sub(r"\s+", " ", unescape(item or "")).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        clean.append(item)
        if len(clean) >= limit:
            break
    return ";".join(clean)


def crawl(max_pages_per_entity: int, max_depth: int, delay: float, timeout: float) -> list[dict[str, str]]:
    seeds = load_seeds()
    existing_urls = {canonicalize_url(seed.url) for seed in seeds}
    seed_by_url = {canonicalize_url(seed.url): seed for seed in seeds}

    queue: deque[tuple[str, str, str, int]] = deque()
    for seed in seeds:
        queue.append((seed.entity_id, seed.url, seed.source_id, 0))

    seen: set[tuple[str, str]] = set()
    counts_by_entity: Counter[str] = Counter()
    rows: list[dict[str, str]] = []

    while queue:
        entity_id, url, linked_from, depth = queue.popleft()
        url = canonicalize_url(url)
        key = (entity_id, url)
        if key in seen:
            continue
        if counts_by_entity[entity_id] >= max_pages_per_entity:
            continue
        if not allowed_url(url):
            continue

        seen.add(key)
        counts_by_entity[entity_id] += 1

        status_code = ""
        final_url = url
        title = ""
        text = ""
        links: list[str] = []
        fields: list[str] = []
        error = ""

        try:
            status_code, final_url, content_type, body = fetch_url(url, timeout=timeout)
            if "html" not in content_type and body.lstrip()[:1] != "<":
                error = f"non_html_content_type={content_type}"
            else:
                title, text, links, fields = parse_html(body)
        except RuntimeError as exc:
            error = f"fetch_error={exc}"

        page_kind, keyword_hits = classify_page(final_url, title, text)
        status, confidence = source_status(final_url, page_kind, existing_urls)
        seed = seed_by_url.get(url)
        source_id = seed.source_id if seed else ""
        candidate_source_id = source_id or f"SRC-{entity_id}-{slug_for_url(final_url)}"
        phones = PHONE_RE.findall(text)
        emails = EMAIL_RE.findall(text)

        rows.append(
            {
                "inventory_id": f"WPI-{len(rows) + 1:04d}",
                "entity_id": entity_id,
                "url": final_url,
                "status_code": status_code,
                "depth": str(depth),
                "title": title[:240],
                "page_kind": page_kind,
                "keyword_hits": ";".join(keyword_hits),
                "language_hint": language_hint(text),
                "phone_candidates": compact(phones),
                "email_candidates": compact(emails),
                "form_fields": compact(fields, limit=20),
                "candidate_source_id": candidate_source_id,
                "linked_from": linked_from,
                "source_status": status,
                "confidence": confidence,
                "last_checked": TODAY,
                "notes": error,
            }
        )

        host = urlparse(final_url).netloc.lower()
        if depth < max_depth and not error and host not in NO_DEEP_CRAWL_HOSTS:
            for href in links:
                next_url = canonicalize_url(urljoin(final_url, href))
                if allowed_url(next_url):
                    queue.append((entity_id, next_url, candidate_source_id, depth + 1))

        if delay:
            time.sleep(delay)

    rows.sort(key=lambda row: (row["entity_id"], row["source_status"], row["page_kind"], row["url"]))
    for index, row in enumerate(rows, start=1):
        row["inventory_id"] = f"WPI-{index:04d}"
    return rows


def write_report(rows: list[dict[str, str]]) -> None:
    status_counts = Counter(row["source_status"] for row in rows)
    kind_counts = Counter(row["page_kind"] for row in rows)
    entity_counts = Counter(row["entity_id"] for row in rows)
    candidates = [row for row in rows if row["source_status"] == "official_candidate"]
    lines = [
        "# Water Establishment Scrape Run Report",
        "",
        f"Generated: {TODAY}",
        "",
        "## Counts",
        "",
        f"- Pages inventoried: {len(rows)}",
        f"- Existing source pages: {status_counts.get('existing_source', 0)}",
        f"- Official candidate pages: {status_counts.get('official_candidate', 0)}",
        f"- Low-signal official pages: {status_counts.get('low_signal_official_page', 0)}",
        "",
        "## Entity Counts",
        "",
    ]
    for entity, count in sorted(entity_counts.items()):
        lines.append(f"- {entity}: {count}")
    lines.extend(["", "## Page Kinds", ""])
    for kind, count in sorted(kind_counts.items()):
        lines.append(f"- {kind}: {count}")
    lines.extend(["", "## Candidate Pages To Review", ""])
    if candidates:
        for row in candidates[:60]:
            lines.append(
                f"- `{row['candidate_source_id']}` [{row['entity_id']}] {row['page_kind']}: {row['title'] or row['url']} - {row['url']}"
            )
    else:
        lines.append("- None")
    lines.append("")
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages-per-entity", type=int, default=45)
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    headers = [
        "inventory_id",
        "entity_id",
        "url",
        "status_code",
        "depth",
        "title",
        "page_kind",
        "keyword_hits",
        "language_hint",
        "phone_candidates",
        "email_candidates",
        "form_fields",
        "candidate_source_id",
        "linked_from",
        "source_status",
        "confidence",
        "last_checked",
        "notes",
    ]
    rows = crawl(args.max_pages_per_entity, args.max_depth, args.delay, args.timeout)
    write_csv(OUT_INVENTORY, rows, headers)
    write_report(rows)
    print(f"Wrote {len(rows)} rows to {OUT_INVENTORY.relative_to(ROOT)}")
    print(f"Wrote report to {OUT_REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
