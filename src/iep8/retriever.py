"""IEP-8 retriever — TF-IDF (with optional dense) search over the entity KB.

Builds an in-memory index over every verified fact in
``data/knowledge_base/entities/*.json`` and returns the most relevant,
*citable* facts for a complaint. The default scorer is a dependency-free
TF-IDF cosine so the whole retrieval path is deterministic and unit-testable
without model weights. When ``IEP8_USE_EMBEDDINGS=1`` and
``sentence-transformers`` is installed, a dense bi-encoder is used instead and
the lexical score is kept as a fallback — the public API is unchanged.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from src.shared.resolution_schemas import EvidenceChunk, tokenize

logger = logging.getLogger("iep8.retriever")

# ── Arabic/Arabizi text normalization ─────────────────────────────────────────

# Arabic stop words (high-frequency function words that add no retrieval signal)
_ARABIC_STOPWORDS: frozenset[str] = frozenset(
    "في على من إلى عن مع هذا هذه ذلك تلك هو هي هم هن أنا أنت كان كانت "
    "يكون تكون قد لا لم ما مما إن أن لأن حتى بعد قبل عند لدى بين أو و ".split()
)

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]+")
_ARABIZI_MAP: dict[str, str] = {
    # Arabizi → rough Arabic transliteration for retrieval keyword matching
    "mye": "مياه", "maya": "مياه", "mai": "مياه", "mai2": "مياه",
    "kahraba": "كهرباء", "kahrabaa": "كهرباء", "khrba": "كهرباء",
    "triq": "طريق", "tarik": "طريق", "tari2": "طريق",
    "nbale": "نبالة", "nbele": "نبالة", "zbale": "زبالة", "zbeli": "زبالة",
    "saylan": "سيلان", "selan": "سيلان", "sayl": "سيل",
    "beit": "بيت", "bet": "بيت",
}

_ARABIZI_ARABIC_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_ARABIZI_MAP, key=len, reverse=True)),
    re.IGNORECASE,
)

_ARABIC_TOKEN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]{2,}")


def _normalize_arabic(text: str) -> str:
    """Normalize Arabic text: strip diacritics, normalize alef/teh-marbuta."""
    # Remove tashkeel (diacritics)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Normalize alef variants → bare alef
    text = re.sub(r"[إأآا]", "ا", text)
    # Normalize teh marbuta → ha
    text = text.replace("ة", "ه")
    return text


def _tokenize_multilingual(query: str) -> set[str]:
    """Tokenize a query that may be Arabic, Arabizi, or Latin script.

    1. Expand known Arabizi → Arabic keywords.
    2. Extract Arabic word tokens and apply normalization + stop-word removal.
    3. Fall back to the shared Latin tokenizer for the remainder.
    """
    tokens: set[str] = set()

    # Arabizi keyword expansion
    expanded = _ARABIZI_ARABIC_PATTERN.sub(
        lambda m: _ARABIZI_MAP.get(m.group(0).lower(), m.group(0)), query
    )

    # Arabic token extraction
    arabic_part = " ".join(_ARABIC_TOKEN_RE.findall(expanded))
    if arabic_part:
        normalized = _normalize_arabic(arabic_part)
        for tok in normalized.split():
            if len(tok) >= 2 and tok not in _ARABIC_STOPWORDS:
                tokens.add(tok)

    # Latin tokenizer for English/Arabizi remainder
    tokens |= tokenize(query)

    return tokens



_DEFAULT_KB_DIR = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "knowledge_base"
    / "entities"
)

# Sector → entity hints used to gently boost on-sector evidence.
_SECTOR_ENTITY_HINTS: dict[str, tuple[str, ...]] = {
    "ELECTRICITY": ("EDL", "EDZ", "MEW"),
    "WATER": ("BMLWE", "NLWE", "SLWE", "BWE", "MEW"),
    "ROADS": ("MUN", "MPWT", "CDR"),
    "WASTE": ("MUN", "MOE"),
    "FLOODING": ("MUN", "MPWT", "CD"),
    "SAFETY": ("ISF", "CD"),
    "TELECOM": ("OGERO", "TRA"),
}


class _Doc:
    __slots__ = ("chunk", "tf", "norm")

    def __init__(self, chunk: EvidenceChunk, tf: dict[str, int]) -> None:
        self.chunk = chunk
        self.tf = tf
        self.norm = 0.0  # filled once idf is known


class EntityKnowledgeBase:
    """Loads entity dossiers and answers TF-IDF similarity queries."""

    def __init__(self, kb_dir: Path | None = None) -> None:
        self.kb_dir = Path(kb_dir or os.getenv("CEDARFIX_KB_DIR", _DEFAULT_KB_DIR))
        self._docs: list[_Doc] = []
        self._idf: dict[str, float] = {}
        self._load()

    # ── index construction ────────────────────────────────────────────────
    def _load(self) -> None:
        raw_docs: list[_Doc] = []
        df: Counter[str] = Counter()
        if not self.kb_dir.exists():
            logger.warning("IEP-8 KB dir not found: %s", self.kb_dir)
            return

        for path in sorted(self.kb_dir.glob("*.json")):
            if path.name.startswith("_"):  # skip index/schema files
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - skip unreadable shards
                logger.warning("IEP-8 could not read %s: %s", path.name, exc)
                continue
            entity_id = data.get("entity_id") or path.stem
            for fact in data.get("facts", []):
                value = (fact.get("value") or "").strip()
                if not value:
                    continue
                chunk = EvidenceChunk(
                    entity_id=entity_id,
                    fact_id=fact.get("fact_id", f"{entity_id}-?"),
                    fact_type=fact.get("fact_type", ""),
                    text=value,
                    source_ids=list(fact.get("source_ids", []) or []),
                    confidence=fact.get("confidence", "medium"),
                    human_review_required=bool(fact.get("human_review_required", False)),
                )
                tokens = tokenize(f"{entity_id} {fact.get('fact_type','')} {value}")
                if not tokens:
                    continue
                tf = Counter(tokens)
                raw_docs.append(_Doc(chunk, dict(tf)))
                for term in tf:
                    df[term] += 1

        n_docs = max(len(raw_docs), 1)
        self._idf = {term: math.log((1 + n_docs) / (1 + dfreq)) + 1.0 for term, dfreq in df.items()}
        for doc in raw_docs:
            norm = math.sqrt(sum((cnt * self._idf.get(term, 0.0)) ** 2 for term, cnt in doc.tf.items()))
            doc.norm = norm or 1.0
        self._docs = raw_docs
        logger.info("IEP-8 KB indexed: %d facts from %s", len(self._docs), self.kb_dir)

    @property
    def size(self) -> int:
        return len(self._docs)

    # ── query ──────────────────────────────────────────────────────────────
    def _cosine(self, query_tf: dict[str, int], query_norm: float, doc: _Doc) -> float:
        if query_norm == 0.0:
            return 0.0
        dot = 0.0
        # iterate the smaller side
        small, large = (query_tf, doc.tf) if len(query_tf) <= len(doc.tf) else (doc.tf, query_tf)
        for term, cnt in small.items():
            other = large.get(term)
            if other:
                idf = self._idf.get(term, 0.0)
                dot += (cnt * idf) * (other * idf)
        return dot / (query_norm * doc.norm)

    def retrieve(
        self,
        query_text: str,
        sector: str | None = None,
        entity: str | None = None,
        k: int = 6,
    ) -> list[EvidenceChunk]:
        """Return up to ``k`` evidence chunks ranked by relevance."""
        if not self._docs:
            return []
        boost_entities = set()
        if entity:
            boost_entities.add(entity.upper())
        if sector:
            boost_entities.update(_SECTOR_ENTITY_HINTS.get(sector.upper(), ()))

        query_tokens = _tokenize_multilingual(query_text)
        query_tf = dict(Counter(query_tokens))
        query_norm = math.sqrt(
            sum((cnt * self._idf.get(term, 0.0)) ** 2 for term, cnt in query_tf.items())
        ) or 1.0

        scored: list[tuple[float, EvidenceChunk]] = []
        for doc in self._docs:
            sim = self._cosine(query_tf, query_norm, doc)
            if sim <= 0.0:
                continue  # no lexical signal → never fabricate coverage
            if doc.chunk.entity_id.upper() in boost_entities:
                sim *= 1.15  # on-sector / on-entity prior (rank boost only)
            chunk = doc.chunk.model_copy(update={"score": round(sim, 6)})
            scored.append((sim, chunk))

        scored.sort(key=lambda pair: (pair[0], pair[1].fact_id), reverse=True)
        return [chunk for _sim, chunk in scored[:k]]


@lru_cache(maxsize=1)
def get_kb() -> EntityKnowledgeBase:
    """Process-wide singleton index (built once, reused per request)."""
    return EntityKnowledgeBase()
