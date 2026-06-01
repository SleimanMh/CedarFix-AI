"""Multilingual learned classifier for IEP-1.

The runtime safety story remains hybrid: this model proposes a semantic
sector/issue hypothesis from noisy citizen text, while the vocabulary rules,
KB router, and HITL gates decide whether the result is safe to automate.

Architecture (three-tier cascade):
  1. If sentence-transformers is installed AND CEDARFIX_IEP1_USE_MULTILINGUAL=1,
     use ``paraphrase-multilingual-MiniLM-L12-v2`` embeddings + cosine-similarity
     search over a labelled prototype pool. Handles Arabic, Arabizi, English.
  2. If Arabic script is detected in the input, supplement the char-gram SGD
     with an Arabic keyword scorer and combine scores via weighted vote.
     This fixes the 0 % Arabic accuracy observed on gold OOD evaluation.
  3. Fall back to the original hashed char-gram SGD, which remains the primary
     path for Arabizi / English text.

Environment variables:
  CEDARFIX_IEP1_SEMANTIC_MODEL=0         disable all learned models
  CEDARFIX_IEP1_USE_MULTILINGUAL=1       enable sentence-transformers tier
  CEDARFIX_IEP1_SEMANTIC_MAX_EXAMPLES    training-corpus cap (default 6000)
  CEDARFIX_IEP1_SEMANTIC_MAX_PER_LABEL   per-label cap for balance (default 180)
  CEDARFIX_IEP1_SEMANTIC_MAX_SCAN        max JSONL lines to read (default 90000)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger("iep1.semantic_classifier")

ROOT = Path(__file__).resolve().parents[2]
# TRAIN-ONLY. The validation and locked-test files are deliberately excluded so
# the ablation in scripts/evaluate_ai_ablation.py reports leakage-free numbers.
# Adding val/test here would let the char-gram model memorize eval spellings.
TRAINING_PATHS = (
    ROOT / "data" / "training" / "cidarfix_v29_batch8_train_v14_enriched.jsonl",
)

MODEL_NAME = "cedarfix-multilingual-ensemble-v1"
_CHARGRAM_MODEL_NAME = "cedarfix-hashed-chargram-sgd-v1"
DEFAULT_MAX_EXAMPLES = int(os.getenv("CEDARFIX_IEP1_SEMANTIC_MAX_EXAMPLES", "6000"))
DEFAULT_MAX_PER_LABEL = int(os.getenv("CEDARFIX_IEP1_SEMANTIC_MAX_PER_LABEL", "180"))
DEFAULT_MAX_SCAN = int(os.getenv("CEDARFIX_IEP1_SEMANTIC_MAX_SCAN", "90000"))

# ──────────────────────────────────────────────────────────────────────────────
# Arabic-script detection
# ──────────────────────────────────────────────────────────────────────────────
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06ff]")

def _arabic_ratio(text: str) -> float:
    """Fraction of non-space characters that are Arabic-script."""
    chars = [c for c in text if c != " "]
    if not chars:
        return 0.0
    return sum(1 for c in chars if "\u0600" <= c <= "\u06ff") / len(chars)


# ──────────────────────────────────────────────────────────────────────────────
# Arabic keyword scorer
# Built from the same keyword tables used in route_complaint.py so the two
# systems always agree on Arabic vocabulary. Sector scores are normalised to
# a soft-max distribution for ensemble mixing.
# ──────────────────────────────────────────────────────────────────────────────
_ARABIC_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "WATER": [
        "مياه", "ماء", "مي", "تسرب", "تسريب", "انبوب", "أنبوب", "ماسورة", "شبكة مياه",
        "مجاري", "صرف", "مجرور", "مجارير", "ضغط", "ريحة", "وسخة", "ملوثة", "عكرة",
        "حمراء", "فاتورة مياه", "عداد مياه", "اشتراك مياه", "مياه الصرف",
    ],
    "ELECTRICITY": [
        "كهرباء", "تيار كهربائي", "انقطاع الكهرباء", "كهربا", "لمبة", "سلك كهربائي",
        "عمود كهربائي", "محول", "تعريفة", "فاتورة كهرباء", "عداد كهربائي",
        "شرارة", "شرر", "حريق كهربائي", "كابل مكشوف",
    ],
    "ROADS": [
        "طريق", "شارع", "حفرة", "أسفلت", "رصيف", "تراجع", "انهيار طريق",
        "اشارة مرور", "إشارة مرور", "جسر", "نفق", "حاجز", "طريق مقطوع",
        "طريق وطنية", "طريق فرعية", "الوزارة",
    ],
    "TELECOM": [
        "انترنت", "إنترنت", "اتصالات", "هاتف", "خط ارضي", "خط أرضي", "أوجيرو",
        "اوجيرو", "دي اس ال", "فايبر", "واي فاي", "راوتر", "كابينة",
        "كابل مقطوع", "فاتورة هاتف",
    ],
    "WASTE": [
        "زبالة", "نفايات", "قمامة", "حاوية", "برميل زبالة", "حريق نفايات",
        "نفايات طبية", "نفايات صناعية", "رمي نفايات", "تلوث", "دفان",
    ],
    "FLOODING": [
        "فيضان", "غرق", "ماء عارم", "طريق غارقة", "بالوعة مسدودة",
        "مجرور مسدود", "مياه عارمة", "سرداب", "طابق سفلي",
        "المي دخل", "غرقانة",
    ],
    "SAFETY": [
        "حادث", "إطلاق نار", "انفجار", "حريق", "إسعاف", "دفاع مدني", "خطر",
        "حيوانات شاردة", "انهيار", "غاز", "مسلح", "تهديد",
    ],
    "ENVIRONMENT": [
        "تلوث هواء", "تلوث نهر", "تلوث شاطئ", "نباتات ضارة", "محمية طبيعية",
        "دخان صناعي", "مصنع ملوث",
    ],
}

# Issue-type hints per sector (maps Arabic phrases → issue type suffix).
_ARABIC_ISSUE_HINTS: dict[str, list[tuple[str, str]]] = {
    "WATER": [
        (r"مجاري|صرف|مجرور", "sewage_flooding"),
        (r"تسرب|ماسورة|انبوب|أنبوب", "pipe_leak"),
        (r"وسخ|ملوث|عكر", "water_quality"),
        (r"ضغط", "low_pressure"),
        (r"فاتورة|عداد", "billing"),
    ],
    "ELECTRICITY": [
        (r"سلك مكشوف|كابل مكشوف|شرارة|شرر", "exposed_wire"),
        (r"محول|حريق كهربائي", "transformer_fire"),
        (r"انقطاع|ما في كهرباء|قطعت", "outage"),
        (r"فاتورة|عداد", "billing"),
    ],
    "ROADS": [
        (r"حفرة|أسفلت", "pothole"),
        (r"جسر|نفق", "bridge_tunnel"),
        (r"حاجز|اشارة|إشارة", "sign_barrier"),
        (r"مقطوع|محجوب", "road_blocked"),
    ],
    "TELECOM": [
        (r"واي فاي|راوتر|موبايل بس", "cpe_device"),
        (r"كابل مقطوع|كابينة", "cable_cut"),
        (r"فاتورة", "billing"),
        (r"الألفا|التاتش|4g|5g|3g", "mobile_network"),
    ],
    "FLOODING": [
        (r"داخل البيت|سرداب|دخل المي", "indoor_flooding"),
        (r"مجرور|بالوعة", "drain_blocked"),
        (r"طريق غارق", "road_flooded"),
    ],
}


def _score_arabic_keywords(text: str) -> dict[str, float]:
    """Score each sector by Arabic keyword hit count (unnormalised)."""
    text_lower = text.lower()
    scores: dict[str, float] = {}
    for sector, keywords in _ARABIC_SECTOR_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw in text_lower)
        if hit > 0:
            scores[sector] = float(hit)
    return scores


def _arabic_issue_hint(sector: str, text: str) -> str:
    """Return best-matching issue-type suffix for an Arabic sector prediction."""
    hints = _ARABIC_ISSUE_HINTS.get(sector, [])
    for pattern, issue_type in hints:
        if re.search(pattern, text, re.IGNORECASE):
            return issue_type
    # Default issue-type map
    defaults = {
        "WATER": "water_quality",
        "ELECTRICITY": "outage",
        "ROADS": "pothole",
        "TELECOM": "connectivity",
        "WASTE": "illegal_dump",
        "FLOODING": "drain_blocked",
        "SAFETY": "emergency",
        "ENVIRONMENT": "pollution",
    }
    return defaults.get(sector, "general")


@dataclass(frozen=True)
class SemanticHypothesis:
    sector: str
    issue_type: str
    label: str
    confidence: float


@dataclass(frozen=True)
class SemanticPrediction:
    model_name: str
    available: bool
    training_examples: int
    label_count: int
    top3: tuple[SemanticHypothesis, ...]
    reason: str

    @property
    def selected(self) -> SemanticHypothesis | None:
        return self.top3[0] if self.top3 else None

    def model_dump(self) -> dict:
        return {
            "model_name": self.model_name,
            "available": self.available,
            "training_examples": self.training_examples,
            "label_count": self.label_count,
            "reason": self.reason,
            "top3": [
                {
                    "sector": item.sector,
                    "issue_type": item.issue_type,
                    "label": item.label,
                    "confidence": item.confidence,
                }
                for item in self.top3
            ],
        }


@dataclass
class _SemanticModel:
    vectorizer: object
    classifier: object
    training_examples: int
    label_count: int


def _split_label(label: str) -> tuple[str, str] | None:
    if "/" not in label:
        return None
    sector, issue_type = label.split("/", 1)
    sector = sector.strip().upper()
    issue_type = issue_type.strip().lower()
    if not sector or not issue_type:
        return None
    return sector, issue_type


def _row_text_and_label(row: dict) -> tuple[str, str] | None:
    label = (row.get("metadata") or {}).get("label")
    user_text = ""
    for message in row.get("messages", []):
        if message.get("role") == "user":
            user_text = str(message.get("content") or "").strip()
            break
    if not label or not user_text or _split_label(str(label)) is None:
        return None
    return user_text, str(label)


def _load_examples(
    *,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
    max_per_label: int = DEFAULT_MAX_PER_LABEL,
    max_scan: int = DEFAULT_MAX_SCAN,
) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    per_label: dict[str, int] = {}
    scanned = 0

    for path in TRAINING_PATHS:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if len(texts) >= max_examples or scanned >= max_scan:
                    break
                scanned += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item = _row_text_and_label(parsed)
                if item is None:
                    continue
                text, label = item
                if per_label.get(label, 0) >= max_per_label:
                    continue
                texts.append(text)
                labels.append(label)
                per_label[label] = per_label.get(label, 0) + 1
        if len(texts) >= max_examples or scanned >= max_scan:
            break

    return texts, labels


@lru_cache(maxsize=1)
def _load_model() -> _SemanticModel | None:
    if os.getenv("CEDARFIX_IEP1_SEMANTIC_MODEL", "1").lower() in {"0", "false", "off"}:
        return None
    try:
        from sklearn.feature_extraction.text import HashingVectorizer
        from sklearn.linear_model import SGDClassifier
    except Exception as exc:  # noqa: BLE001 - runtime degrades to rules-only
        logger.warning("IEP-1 semantic classifier unavailable: %s", exc)
        return None

    texts, labels = _load_examples()
    if len(set(labels)) < 2 or len(texts) < 50:
        logger.warning(
            "IEP-1 semantic classifier disabled: only %d examples / %d labels",
            len(texts),
            len(set(labels)),
        )
        return None

    vectorizer = HashingVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        n_features=2**18,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
    )
    classifier = SGDClassifier(
        loss="log_loss",
        alpha=0.0001,
        max_iter=35,
        tol=1e-3,
        random_state=503,
        class_weight="balanced",
    )
    matrix = vectorizer.transform(texts)
    classifier.fit(matrix, labels)
    logger.info(
        "IEP-1 semantic classifier trained examples=%d labels=%d",
        len(texts),
        len(set(labels)),
    )
    return _SemanticModel(
        vectorizer=vectorizer,
        classifier=classifier,
        training_examples=len(texts),
        label_count=len(set(labels)),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Optional: sentence-transformers multilingual model
# Activated by CEDARFIX_IEP1_USE_MULTILINGUAL=1 and sentence-transformers pkg.
# Uses prototype-mean-pooled embeddings per label for cosine-similarity search.
# ──────────────────────────────────────────────────────────────────────────────
_MULTILINGUAL_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


@dataclass
class _MultilingualModel:
    encoder: object          # SentenceTransformer instance
    prototypes: dict         # label → mean embedding (numpy array)
    training_examples: int
    label_count: int


@lru_cache(maxsize=1)
def _load_multilingual_model() -> Optional["_MultilingualModel"]:
    if os.getenv("CEDARFIX_IEP1_USE_MULTILINGUAL", "0").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        logger.info("sentence-transformers unavailable (%s); falling back to char-gram", exc)
        return None

    texts, labels = _load_examples()
    if len(set(labels)) < 2 or len(texts) < 50:
        return None

    try:
        encoder = SentenceTransformer(_MULTILINGUAL_MODEL_NAME)
        embeddings = encoder.encode(texts, batch_size=64, show_progress_bar=False,
                                     normalize_embeddings=True)
        # Build per-label prototype (mean of normalised embeddings)
        import collections
        label_embs: dict[str, list] = collections.defaultdict(list)
        for emb, lbl in zip(embeddings, labels):
            label_embs[lbl].append(emb)
        prototypes = {
            lbl: np.mean(np.array(vecs), axis=0)
            for lbl, vecs in label_embs.items()
        }
        # Re-normalise prototypes
        for lbl, vec in prototypes.items():
            norm = np.linalg.norm(vec)
            if norm > 0:
                prototypes[lbl] = vec / norm
        logger.info(
            "IEP-1 multilingual model loaded: %d prototypes from %d examples",
            len(prototypes), len(texts),
        )
        return _MultilingualModel(
            encoder=encoder,
            prototypes=prototypes,
            training_examples=len(texts),
            label_count=len(prototypes),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Multilingual model init failed: %s", exc)
        return None


def _multilingual_classify(text: str, top_k: int = 3) -> list[tuple[str, float]]:
    """Return [(label, score)] sorted descending using multilingual embeddings."""
    ml_model = _load_multilingual_model()
    if ml_model is None:
        return []
    try:
        import numpy as np
        emb = ml_model.encoder.encode([text], normalize_embeddings=True)[0]
        scores = {
            lbl: float(np.dot(emb, proto))
            for lbl, proto in ml_model.prototypes.items()
        }
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Multilingual inference failed: %s", exc)
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Arabic keyword tier
# When Arabic script is dominant, produce label hypotheses purely from
# keyword matching. These are combined with the char-gram predictions.
# ──────────────────────────────────────────────────────────────────────────────

def _arabic_keyword_classify(text: str, top_k: int = 3) -> list[tuple[str, float]]:
    """Return [(label, normalised_score)] for Arabic keyword matching."""
    raw = _score_arabic_keywords(text)
    if not raw:
        return []
    total = sum(raw.values())
    results: list[tuple[str, float]] = []
    for sector in sorted(raw, key=lambda s: raw[s], reverse=True)[:top_k]:
        norm_score = raw[sector] / total
        issue_type = _arabic_issue_hint(sector, text)
        label = f"{sector}/{issue_type}"
        results.append((label, round(norm_score, 4)))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def classify_text(text: str, *, top_k: int = 3) -> SemanticPrediction:
    """Return a multilingual top-k issue prediction.

    Cascade:
      1. sentence-transformers (if available and enabled)
      2. Arabic keyword scoring (when Arabic script ≥ 25 % of input)
      3. hashed char-gram SGD
    For Arabic text, tiers 2+3 are blended (Arabic keyword weight = 0.65).
    """
    if not text.strip():
        model = _load_model()
        return SemanticPrediction(
            model_name=MODEL_NAME,
            available=False,
            training_examples=model.training_examples if model else 0,
            label_count=model.label_count if model else 0,
            top3=(),
            reason="empty_text",
        )

    arabic_frac = _arabic_ratio(text)
    is_arabic_dominant = arabic_frac >= 0.25

    # ── Tier 1: sentence-transformers ──
    ml_results = _multilingual_classify(text, top_k=top_k)
    if ml_results:
        hypotheses = []
        for label, score in ml_results:
            split = _split_label(label)
            if split is None:
                continue
            sector, issue_type = split
            hypotheses.append(SemanticHypothesis(
                sector=sector, issue_type=issue_type, label=label,
                confidence=round(float(score), 4),
            ))
        ml_model = _load_multilingual_model()
        return SemanticPrediction(
            model_name=_MULTILINGUAL_MODEL_NAME,
            available=bool(hypotheses),
            training_examples=ml_model.training_examples if ml_model else 0,
            label_count=ml_model.label_count if ml_model else 0,
            top3=tuple(hypotheses),
            reason="multilingual_embeddings",
        )

    # ── Tier 2 + 3: Arabic keyword + char-gram blend ──
    model = _load_model()
    training_examples = model.training_examples if model else 0
    label_count = model.label_count if model else 0

    chargram_scores: dict[str, float] = {}
    if model is not None:
        matrix = model.vectorizer.transform([text])
        probabilities = model.classifier.predict_proba(matrix)[0]
        classes = list(model.classifier.classes_)
        for idx, prob in enumerate(probabilities):
            chargram_scores[str(classes[idx])] = float(prob)

    if is_arabic_dominant:
        arabic_results = _arabic_keyword_classify(text, top_k=top_k)
        arabic_dict: dict[str, float] = {lbl: sc for lbl, sc in arabic_results}

        # Blend: Arabic keyword 0.65 weight, char-gram 0.35
        all_labels = set(arabic_dict) | set(chargram_scores)
        blended: dict[str, float] = {}
        for lbl in all_labels:
            a_score = arabic_dict.get(lbl, 0.0) * 0.65
            c_score = chargram_scores.get(lbl, 0.0) * 0.35
            blended[lbl] = a_score + c_score

        ranked = sorted(blended.items(), key=lambda x: x[1], reverse=True)[:top_k]
        hypotheses = []
        for label, score in ranked:
            split = _split_label(label)
            if split is None:
                continue
            sector, issue_type = split
            hypotheses.append(SemanticHypothesis(
                sector=sector, issue_type=issue_type, label=label,
                confidence=round(score, 4),
            ))
        if hypotheses:
            return SemanticPrediction(
                model_name=MODEL_NAME,
                available=True,
                training_examples=training_examples,
                label_count=label_count,
                top3=tuple(hypotheses),
                reason="arabic_keyword_blend",
            )

    # ── Pure char-gram (Arabizi / English) ──
    if not chargram_scores:
        return SemanticPrediction(
            model_name=MODEL_NAME,
            available=False,
            training_examples=0,
            label_count=0,
            top3=(),
            reason="model_unavailable",
        )

    ranked = sorted(chargram_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    hypotheses = []
    for label, prob in ranked:
        split = _split_label(label)
        if split is None:
            continue
        sector, issue_type = split
        hypotheses.append(SemanticHypothesis(
            sector=sector, issue_type=issue_type, label=label,
            confidence=round(float(prob), 4),
        ))

    return SemanticPrediction(
        model_name=_CHARGRAM_MODEL_NAME,
        available=bool(hypotheses),
        training_examples=training_examples,
        label_count=label_count,
        top3=tuple(hypotheses),
        reason="ok" if hypotheses else "no_valid_labels",
    )
