"""
Absorb Lebanese-priority external Arabizi sources into CedarFix review queues.

This script is intentionally conservative:
  - It does not promote anything into production vocabulary.
  - It does not store raw tweets/messages in the derived review file.
  - It mines source-backed surface tokens as OOV review candidates only.
  - It records license/access constraints in an external source ledger.

Inputs are optional; missing gated/manual sources are recorded in the ledger but
not mined.
"""
from __future__ import annotations

import csv
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARABIZI_DIR = ROOT / "data/knowledge_base/arabizi"
PROJECT_RBZ_ID_PATH = (
    ROOT
    / "data/external_sources/project_rbz/arabizi_identification/Arabizi Identification/arabizi-twitter-leb.csv"
)
PROJECT_RBZ_SENZI_AI_PATH = (
    ROOT
    / "data/external_sources/project_rbz/extracted_partial_senzi/SenZi/Datasets/AI_dataset_4.4K-tweets_balanced.csv"
)
PROJECT_RBZ_SENZI_SA_PATH = (
    ROOT
    / "data/external_sources/project_rbz/extracted_partial_senzi/SenZi/Datasets/SA_dataset_1.6K-tweets_balanced.csv"
)
KAGGLE_RAIDY_PATH = (
    ROOT
    / "data/external_sources/kaggle_raidy_arabizi/extracted/unbalanced-sentiment-arabizi-ds.csv"
)
MANUAL_DROP_DIR = ROOT / "data/external_sources/manual_drop"
MANUAL_SENZI_ZIP = MANUAL_DROP_DIR / "senzi.zip"
MANUAL_SENZI_LARGE_ZIP = MANUAL_DROP_DIR / "senzi-large.zip"
MANUAL_THESIS_ZIP = MANUAL_DROP_DIR / "thesis.zip"

LEDGER_PATH = ARABIZI_DIR / "external_source_ledger.csv"
OOV_PATH = ARABIZI_DIR / "lebanese_external_oov_candidates.csv"
REPORT_PATH = ROOT / "docs/ARABIZI_EXTERNAL_ABSORPTION_REPORT.md"
RL_PATH = ARABIZI_DIR / "arabizi_reliability_layer.json"

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9'._-]{1,30}")
ARABIZI_DIGITS = set("2356789")
ARABIZI_PATTERNS = (
    "kh",
    "gh",
    "sh",
    "ch",
    "aa",
    "ee",
    "ou",
    "2",
    "3",
    "5",
    "6",
    "7",
    "8",
    "9",
)

ENGLISH_STOPWORDS = {
    "the",
    "and",
    "you",
    "your",
    "for",
    "that",
    "with",
    "this",
    "are",
    "was",
    "were",
    "have",
    "has",
    "had",
    "but",
    "not",
    "just",
    "all",
    "can",
    "what",
    "from",
    "they",
    "them",
    "its",
    "our",
    "she",
    "him",
    "her",
    "his",
    "who",
    "how",
    "why",
    "when",
    "where",
    "will",
    "would",
    "could",
    "should",
    "been",
    "out",
    "get",
    "got",
    "one",
    "two",
    "too",
    "use",
    "via",
    "per",
    "now",
    "new",
    "old",
    "day",
    "week",
    "year",
    "like",
    "live",
    "love",
    "good",
    "bad",
    "best",
    "nice",
    "great",
    "hello",
    "hi",
    "hey",
    "lol",
    "lmao",
    "omg",
    "rt",
    "http",
    "https",
    "www",
    "com",
    "amp",
}

OBVIOUS_ENTITY_OR_NOISE = {
    "najwakaram",
    "liverpool",
    "pepe",
    "messi",
    "ronaldo",
    "facebook",
    "twitter",
    "instagram",
    "youtube",
    "iphone",
    "samsung",
}

HIGH_RISK_TERMS = {
    "khara",
    "ayre",
    "ayri",
    "sharmouta",
    "manyake",
    "7mar",
    "kalb",
    "manyak",
    "nchalla",
    "mout",
    "mawt",
    "dam",
    "nar",
    "7ari2",
    "ghaz",
    "silk",
    "kahraba",
}

LEBANON_PLACE_HINTS = {
    "beirut",
    "berut",
    "bayrut",
    "beyrouth",
    "lebnen",
    "lebnan",
    "lebanon",
    "hamra",
    "tripoli",
    "trablos",
    "saida",
    "tyre",
    "sour",
    "jounieh",
    "jbeil",
    "byblos",
    "baabda",
    "achrafieh",
    "ashrafieh",
    "dahye",
    "bekaa",
}


LEDGER_COLUMNS = [
    "source_id",
    "source_name",
    "url",
    "region",
    "license",
    "access_requirement",
    "allowed_uses",
    "blocked_uses",
    "raw_import_allowed",
    "local_status",
    "local_path",
    "citation_required",
    "notes",
    "verified_by",
    "verified_at",
]

OOV_COLUMNS = [
    "external_candidate_id",
    "surface_form",
    "normalized_form",
    "source_ids",
    "region",
    "observed_count_total",
    "document_count_total",
    "rbz_identification_count",
    "rbz_senzi_ai_count",
    "rbz_senzi_sa_count",
    "kaggle_raidy_count",
    "rbz_senzi_lexicon_count",
    "rbz_senzi_large_count",
    "rbz_thesis_translation_count",
    "arabizi_signal_score",
    "suggested_layer",
    "suggested_category",
    "confidence_level",
    "risk_level",
    "false_friend_risk",
    "allowed_uses",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "decision",
    "must_not_auto_promote",
    "notes",
    "created_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_token(token: str) -> str:
    return token.lower().strip("._-'")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def tokens_from_pipe_or_score_text(text: str) -> list[str]:
    tokens: list[str] = []
    for item in re.split(r"[|\n\r\t]+", text):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            item = item.split(":", 1)[0].strip()
        for raw in TOKEN_RE.findall(item.lower()):
            token = normalize_token(raw)
            if token and not token.replace(".", "", 1).isdigit():
                tokens.append(token)
    return tokens


def iter_zip_tokens(zip_path: Path, names: list[str]) -> list[str]:
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        return []
    tokens: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        available = set(zf.namelist())
        for name in names:
            if name not in available:
                continue
            text = zf.read(name).decode("utf-8", errors="replace")
            tokens.extend(tokens_from_pipe_or_score_text(text))
    return tokens


def iter_senzi_zip_tokens() -> list[str]:
    return iter_zip_tokens(
        MANUAL_SENZI_ZIP,
        [
            "SenZi/Lexicon/senzi.neg.expanded.txt",
            "SenZi/Lexicon/senzi.neg.orig.txt",
            "SenZi/Lexicon/senzi.pos.expanded.txt",
            "SenZi/Lexicon/senzi.pos.orig.txt",
        ],
    )


def iter_senzi_large_zip_tokens() -> list[str]:
    return iter_zip_tokens(
        MANUAL_SENZI_LARGE_ZIP,
        [
            "senzi-large/Lexicon/ft-neg.txt",
            "senzi-large/Lexicon/ft-pos.txt",
            "senzi-large/Lexicon/w2v-neg.txt",
            "senzi-large/Lexicon/w2v-pos.txt",
            "senzi-large/Lexicon/filtered-words/ambiguous/negative.txt",
            "senzi-large/Lexicon/filtered-words/ambiguous/positive.txt",
        ],
    )


def iter_thesis_zip_tokens() -> list[str]:
    return iter_zip_tokens(
        MANUAL_THESIS_ZIP,
        [
            "thesis/Misc/Arabizi-Arabic-Translation-Matrices/rbz-ar.txt",
            "thesis/Misc/Lexicon-Based-Classification-Features/negations.txt",
            "thesis/Misc/Lexicon-Based-Classification-Features/stop-words.txt",
        ],
    )


def collect_known_forms() -> set[str]:
    known: set[str] = set()
    sources = [
        (ARABIZI_DIR / "arabizi_surface_forms_v15.csv", ["surface_form", "canonical_form"]),
        (ARABIZI_DIR / "arabizi_general_word_bank.csv", ["romanized_canonical", "variants"]),
        (ARABIZI_DIR / "arabizi_candidate_bank.csv", ["variants"]),
        (ARABIZI_DIR / "arabizi_protected_combos.csv", ["romanized_canonical", "component_tokens"]),
        (ARABIZI_DIR / "arabizi_stoplist.csv", ["term", "normalized_term"]),
    ]
    for path, columns in sources:
        for row in read_csv(path):
            for col in columns:
                raw = row.get(col, "")
                for part in re.split(r"[;|\s]+", raw.lower()):
                    token = normalize_token(part)
                    if token:
                        known.add(token)
    return known


def iter_source_texts() -> tuple[list[tuple[str, str]], dict[str, int]]:
    texts: list[tuple[str, str]] = []
    docs_by_source: dict[str, int] = defaultdict(int)

    # RBZ Arabizi identification, Lebanon-positive rows only.
    for row in read_csv(PROJECT_RBZ_ID_PATH):
        if row.get("arabizi", "").strip() == "1":
            text = row.get("tweet_filter", "")
            if text:
                texts.append(("RBZ_LEB_AI_2016", text))
                docs_by_source["RBZ_LEB_AI_2016"] += 1

    # SenZi AI dataset, Arabizi-positive rows only.
    for row in read_csv(PROJECT_RBZ_SENZI_AI_PATH):
        if row.get("Arabizi", "").strip() == "1":
            text = row.get("tweet_filter", "")
            if text:
                texts.append(("RBZ_SENZI_AI_2019", text))
                docs_by_source["RBZ_SENZI_AI_2019"] += 1

    # SenZi sentiment dataset: all rows are Arabizi sentiment examples.
    for row in read_csv(PROJECT_RBZ_SENZI_SA_PATH):
        text = row.get("tweet", "")
        if text:
            texts.append(("RBZ_SENZI_SA_2019", text))
            docs_by_source["RBZ_SENZI_SA_2019"] += 1

    # Kaggle Raidy Lebanese Arabizi sentiment dataset, CC0 according to Kaggle metadata.
    for row in read_csv(KAGGLE_RAIDY_PATH):
        text = row.get("tweet", "")
        if text:
            texts.append(("KAGGLE_RAIDY_CC0_2020", text))
            docs_by_source["KAGGLE_RAIDY_CC0_2020"] += 1

    # Clean manual Project RBZ ZIPs contain lexicon resources that were not
    # available from the first partial extraction. Treat each surface form as a
    # review-only source item, never as trusted vocabulary.
    for token in iter_senzi_zip_tokens():
        texts.append(("RBZ_SENZI_LEXICON_2019", token))
        docs_by_source["RBZ_SENZI_LEXICON_2019"] += 1

    for token in iter_senzi_large_zip_tokens():
        texts.append(("RBZ_SENZI_LARGE_2020", token))
        docs_by_source["RBZ_SENZI_LARGE_2020"] += 1

    for token in iter_thesis_zip_tokens():
        texts.append(("RBZ_THESIS_TRANSLITERATION_2020", token))
        docs_by_source["RBZ_THESIS_TRANSLITERATION_2020"] += 1

    return texts, dict(docs_by_source)


def token_signal(token: str, doc_count: int) -> int:
    score = 0
    if any(ch in ARABIZI_DIGITS for ch in token):
        score += 2
    if any(pattern in token for pattern in ARABIZI_PATTERNS):
        score += 1
    if doc_count >= 2:
        score += 1
    if token in LEBANON_PLACE_HINTS:
        score += 1
    return score


def classify_token(token: str, count: int, doc_count: int, source_counts: Counter[str]) -> tuple[str, str, str, str, str, str]:
    signal = token_signal(token, doc_count)
    false_friend = "true" if len(token) <= 3 or token in {"aa", "ee", "ha", "la", "ma", "fi"} else "false"
    risk = "LOW"
    layer = "GENERAL_WORD_REVIEW"
    category = "external_oov_support"
    confidence = "MEDIUM" if count >= 5 or signal >= 3 else "LOW"

    if token in HIGH_RISK_TERMS:
        risk = "HIGH"
        layer = "SAFETY_OR_PROFANITY_REVIEW"
        category = "high_risk_term"
        confidence = "MEDIUM"
        false_friend = "true"
    elif token in OBVIOUS_ENTITY_OR_NOISE:
        risk = "MEDIUM"
        layer = "STOPLIST_REVIEW"
        category = "entity_or_noise"
        confidence = "LOW"
    elif token in LEBANON_PLACE_HINTS:
        layer = "LOCATION_SUPPORT_REVIEW"
        category = "place_hint"
        confidence = "MEDIUM"
    elif any(ch in ARABIZI_DIGITS for ch in token):
        layer = "SURFACE_FORM_REVIEW"
        category = "digit_variant"
    elif count >= 10 and doc_count >= 10:
        layer = "GENERAL_WORD_REVIEW"
        category = "frequent_lebanese_support"
    elif len(source_counts) >= 2:
        layer = "CROSS_SOURCE_SUPPORT_REVIEW"
        category = "cross_source_oov"
        confidence = "MEDIUM"

    return layer, category, confidence, risk, false_friend, str(signal)


def build_ledger() -> list[dict[str, str]]:
    verified_at = now_iso()
    return [
        {
            "source_id": "RBZ_LEB_AI_2016",
            "source_name": "Project RBZ Arabizi Identification in Twitter Data - Lebanon subset",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Public ZIP download",
            "allowed_uses": "oov_mining|language_id_eval|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|production_routing_without_native_review",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "DOWNLOADED_AND_EXTRACTED",
            "local_path": "data/external_sources/project_rbz/arabizi_identification",
            "citation_required": "Tobaili 2016 Arabizi identification in Twitter data",
            "notes": "Only Arabizi-positive Lebanon rows mined; raw text not copied into trusted vocab.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "RBZ_SENZI_AI_2019",
            "source_name": "Project RBZ SenZi Arabizi/Not-Arabizi dataset",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon / Lebanese Arabizi project",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Public ZIP download",
            "allowed_uses": "oov_mining|language_id_eval|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|production_routing_without_native_review",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "PARTIAL_ARCHIVE_EXTRACTED_CORE_FILES",
            "local_path": "data/external_sources/project_rbz/extracted_partial_senzi/SenZi/Datasets/AI_dataset_4.4K-tweets_balanced.csv",
            "citation_required": "Tobaili et al. 2019 SenZi",
            "notes": "Archive central directory is corrupt from interrupted download, but core CSV and disclaimer extracted.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "RBZ_SENZI_SA_2019",
            "source_name": "Project RBZ SenZi sentiment dataset",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon / Lebanese Arabizi project",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Public ZIP download",
            "allowed_uses": "oov_mining|sentiment_support_eval|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|production_routing_without_native_review",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "PARTIAL_ARCHIVE_EXTRACTED_CORE_FILES",
            "local_path": "data/external_sources/project_rbz/extracted_partial_senzi/SenZi/Datasets/SA_dataset_1.6K-tweets_balanced.csv",
            "citation_required": "Tobaili et al. 2019 SenZi",
            "notes": "Mined for OOV support terms only; no raw text moved into trusted vocab.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "KAGGLE_RAIDY_CC0_2020",
            "source_name": "Maria J. M. Raidy Lebanese Arabizi sentiment tweets",
            "url": "https://www.kaggle.com/datasets/mariajmraidy/datasets-for-sentiment-analysis-of-arabizi/data",
            "region": "Lebanon",
            "license": "CC0 Public Domain according to Kaggle dataset metadata",
            "access_requirement": "Public Kaggle API download",
            "allowed_uses": "oov_mining|evaluation_candidate_generation|noncommercial_or_commercial_if_cc0|citation_recommended",
            "blocked_uses": "auto_promotion|production_routing_without_native_review|raw_sensitive_text_in_demo",
            "raw_import_allowed": "YES_CC0_WITH_SENSITIVITY_REVIEW",
            "local_status": "DOWNLOADED_AND_EXTRACTED",
            "local_path": "data/external_sources/kaggle_raidy_arabizi/extracted/unbalanced-sentiment-arabizi-ds.csv",
            "citation_required": "Dataset citation recommended; raw text is CC0 but sensitive social content should be filtered.",
            "notes": "Explicit Lebanese Arabizi tweets with geotagging in Lebanon per Kaggle card.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "RBZ_SENZI_LEXICON_2019",
            "source_name": "Project RBZ SenZi original and expanded Arabizi sentiment lexicons",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon / Lebanese Arabizi project",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Manual public ZIP download",
            "allowed_uses": "oov_mining|sentiment_support_eval|surface_form_review|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|direct_routing",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "MANUAL_DROP_AVAILABLE",
            "local_path": "data/external_sources/manual_drop/senzi.zip",
            "citation_required": "Tobaili et al. 2019 SenZi",
            "notes": "Lexicon tokens mined as review-only surface forms; not used as issue labels.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "RBZ_SENZI_LARGE_2020",
            "source_name": "Project RBZ SenZi-Large lexical induction resources",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon / Lebanese Arabizi project",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Manual public ZIP download",
            "allowed_uses": "oov_mining|surface_form_review|stress_test_generation|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|direct_routing",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "MANUAL_DROP_AVAILABLE",
            "local_path": "data/external_sources/manual_drop/senzi-large.zip",
            "citation_required": "Tobaili et al. 2019 SenZi; Tobaili 2020 lexical induction",
            "notes": "Induced forms are noisy and must stay review-only.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "RBZ_THESIS_TRANSLITERATION_2020",
            "source_name": "Project RBZ thesis translation matrices and negation/stopword support lists",
            "url": "https://tahatobaili.github.io/project-rbz/",
            "region": "Lebanon / Lebanese Arabizi project",
            "license": "Non-commercial research use only; citation required per included Disclaimer.txt",
            "access_requirement": "Manual public ZIP download",
            "allowed_uses": "transliteration_review|negation_support_review|oov_mining|noncommercial_research|citation_required",
            "blocked_uses": "commercial_use|auto_promotion|raw_publication_without_review|direct_routing",
            "raw_import_allowed": "LIMITED_NONCOMMERCIAL",
            "local_status": "MANUAL_DROP_AVAILABLE",
            "local_path": "data/external_sources/manual_drop/thesis.zip",
            "citation_required": "Tobaili 2020 PhD thesis",
            "notes": "Translation matrix terms are useful for normalization review, not direct routing.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "ALADDINBENCH_GATED",
            "source_name": "AladdinBench Arabizi messages",
            "url": "https://huggingface.co/datasets/palmaoui/AladdinBench",
            "region": "Lebanon/Egypt/Algeria",
            "license": "Gated; terms must be accepted before use",
            "access_requirement": "Hugging Face gated access request",
            "allowed_uses": "future_eval_reference_after_access",
            "blocked_uses": "import_before_access|auto_promotion",
            "raw_import_allowed": "NO_ACCESS_YET",
            "local_status": "NOT_DOWNLOADED_GATED",
            "local_path": "",
            "citation_required": "Follow dataset card after access.",
            "notes": "High-value future Lebanese subset if accessible.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "QADI_LB_TWEET_IDS",
            "source_name": "QADI Lebanon tweet ID subset",
            "url": "https://github.com/qcri/QADI",
            "region": "Lebanon",
            "license": "Tweet IDs only; Twitter/X terms and hydration constraints apply",
            "access_requirement": "Hydration required; raw text not distributed",
            "allowed_uses": "future_dialect_id_eval_if_hydrated_legally",
            "blocked_uses": "raw_import_without_hydration_compliance|auto_promotion",
            "raw_import_allowed": "NO_RAW_TEXT",
            "local_status": "NOT_DOWNLOADED",
            "local_path": "",
            "citation_required": "QADI paper/repo citation required if used.",
            "notes": "Lebanon-labeled but not Arabizi-specific.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "SHAMI_LEBANESE_APACHE_2018",
            "source_name": "Shami Dialect Corpus Lebanese subset",
            "url": "https://github.com/GU-CLASP/shami-corpus",
            "region": "Lebanon / Levant",
            "license": "Apache-2.0",
            "access_requirement": "Public GitHub repository",
            "allowed_uses": "arabic_script_lebanese_eval|dialect_grounding|non_routing_reference",
            "blocked_uses": "arabizi_claims|auto_promotion|auto_promotion_to_arabizi_vocab",
            "raw_import_allowed": "YES_APACHE2_WITH_CITATION",
            "local_status": "NOT_DOWNLOADED",
            "local_path": "",
            "citation_required": "Qwaider et al. 2018 Shami corpus",
            "notes": "Arabic-script Lebanese subset; useful for Lebanese dialect grounding, not Arabizi surface expansion.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "ARSENTD_LEV_LEBANON_2019",
            "source_name": "ArSenTD-LEV Lebanon subset",
            "url": "https://huggingface.co/datasets/ramybaly/arsentd_lev",
            "region": "Lebanon / Levant",
            "license": "Other; must read and agree to linked OMA license",
            "access_requirement": "Public Hugging Face dataset with external license terms",
            "allowed_uses": "arabic_script_lebanese_sentiment_eval_after_license_review",
            "blocked_uses": "import_before_license_review|arabizi_claims|auto_promotion",
            "raw_import_allowed": "PENDING_LICENSE_REVIEW",
            "local_status": "NOT_DOWNLOADED",
            "local_path": "",
            "citation_required": "Baly et al. 2019 ArSenTD-LEV",
            "notes": "4,000 Levantine Arabic tweets, equally from Jordan/Lebanon/Syria/Palestine. Arabic script, not Arabizi.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "HF_ARABIZI_TRANSLITERATION_LICENSE_BLANK",
            "source_name": "arbml/Arabizi_Transliteration local Hugging Face snapshot",
            "url": "https://huggingface.co/datasets/arbml/Arabizi_Transliteration",
            "region": "Mixed / unclear",
            "license": "Blank in dataset_infos.json",
            "access_requirement": "Local manual drop exists; license must be clarified",
            "allowed_uses": "schema_inspection_only_until_license_clarified",
            "blocked_uses": "raw_import|training|auto_promotion|public_redistribution",
            "raw_import_allowed": "NO_LICENSE_YET",
            "local_status": "MANUAL_DROP_AVAILABLE_BUT_BLOCKED",
            "local_path": "data/external_sources/manual_drop/Arabizi_Transliteration_Dataset",
            "citation_required": "Unknown until license/source clarified.",
            "notes": "21,499 transliteration pairs locally present, but license metadata is empty.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "HAIFACLG_ARABIZI_LICENSE_UNCLEAR",
            "source_name": "HaifaCLG Arabizi code-switching corpus",
            "url": "https://github.com/HaifaCLG/Arabizi",
            "region": "Mixed Arabizi / code-switching",
            "license": "No explicit license found in downloaded README",
            "access_requirement": "Manual ZIP exists; license clarification required",
            "allowed_uses": "methodology_reference|code_switching_schema_reference",
            "blocked_uses": "raw_import|training|auto_promotion|public_redistribution_without_license",
            "raw_import_allowed": "NO_LICENSE_YET",
            "local_status": "MANUAL_DROP_AVAILABLE_BUT_BLOCKED",
            "local_path": "data/external_sources/manual_drop/Arabizi-main.zip",
            "citation_required": "Shehadi and Wintner 2022 if used.",
            "notes": "Useful for code-switching ideas, not Lebanese-specific and license unclear.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
        {
            "source_id": "LEBEVAL_2025_REFERENCE",
            "source_name": "LebEval benchmark from Fine-Tuning LLMs for Low-Resource Dialect Translation: The Case of Lebanese",
            "url": "https://arxiv.org/abs/2505.00114",
            "region": "Lebanon",
            "license": "Dataset availability not verified",
            "access_requirement": "Paper/source follow-up required",
            "allowed_uses": "future_reference_after_dataset_access",
            "blocked_uses": "claim_as_available_dataset|auto_promotion",
            "raw_import_allowed": "NO_ACCESS_YET",
            "local_status": "NOT_DOWNLOADED",
            "local_path": "",
            "citation_required": "Cite paper if methodology used.",
            "notes": "Relevant Lebanese benchmark lead, but no clean downloadable dataset found in this pass.",
            "verified_by": "Codex",
            "verified_at": verified_at,
        },
    ]


def mine_oov_candidates(max_rows: int = 2000) -> tuple[list[dict[str, str]], dict[str, int]]:
    known = collect_known_forms()
    texts, docs_by_source = iter_source_texts()
    token_counts: Counter[str] = Counter()
    doc_counts: Counter[str] = Counter()
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for source_id, text in texts:
        tokens = []
        for raw in TOKEN_RE.findall(text.lower()):
            token = normalize_token(raw)
            if not token or len(token) < 2:
                continue
            tokens.append(token)
            token_counts[token] += 1
            source_counts[token][source_id] += 1
        for token in set(tokens):
            doc_counts[token] += 1

    rows: list[dict[str, str]] = []
    for token, count in token_counts.items():
        if token in known or token in ENGLISH_STOPWORDS:
            continue
        if len(token) < 3 and not any(ch in ARABIZI_DIGITS for ch in token):
            continue
        signal = token_signal(token, doc_counts[token])
        # Keep broad coverage, but require either Arabizi form evidence,
        # cross-document recurrence, or cross-source recurrence.
        if signal < 1 and doc_counts[token] < 3 and len(source_counts[token]) < 2:
            continue

        layer, category, confidence, risk, false_friend, signal_str = classify_token(
            token, count, doc_counts[token], source_counts[token]
        )
        rows.append(
            {
                "surface_form": token,
                "normalized_form": token,
                "source_ids": "|".join(sorted(source_counts[token])),
                "region": "LB_PRIORITY",
                "observed_count_total": str(count),
                "document_count_total": str(doc_counts[token]),
                "rbz_identification_count": str(source_counts[token].get("RBZ_LEB_AI_2016", 0)),
                "rbz_senzi_ai_count": str(source_counts[token].get("RBZ_SENZI_AI_2019", 0)),
                "rbz_senzi_sa_count": str(source_counts[token].get("RBZ_SENZI_SA_2019", 0)),
                "kaggle_raidy_count": str(source_counts[token].get("KAGGLE_RAIDY_CC0_2020", 0)),
                "rbz_senzi_lexicon_count": str(source_counts[token].get("RBZ_SENZI_LEXICON_2019", 0)),
                "rbz_senzi_large_count": str(source_counts[token].get("RBZ_SENZI_LARGE_2020", 0)),
                "rbz_thesis_translation_count": str(source_counts[token].get("RBZ_THESIS_TRANSLITERATION_2020", 0)),
                "arabizi_signal_score": signal_str,
                "suggested_layer": layer,
                "suggested_category": category,
                "confidence_level": confidence,
                "risk_level": risk,
                "false_friend_risk": false_friend,
                "allowed_uses": "oov_review|normalization_candidate_review|stress_test_generation",
                "blocked_uses": "auto_promotion|direct_routing|severity_assignment|production_vocab_without_native_review",
                "review_status": "PENDING_NATIVE_REVIEW",
                "reviewer_id": "UNASSIGNED",
                "decision": "UNREVIEWED",
                "must_not_auto_promote": "true",
                "notes": "Derived from external Lebanese Arabizi sources; raw source text not copied. Review before moving to support layers.",
                "created_at": now_iso(),
            }
        )

    rows.sort(
        key=lambda row: (
            int(row["document_count_total"]),
            int(row["observed_count_total"]),
            int(row["arabizi_signal_score"]),
        ),
        reverse=True,
    )
    rows = rows[:max_rows]
    for i, row in enumerate(rows, start=1):
        row["external_candidate_id"] = f"EXT-LB-OOV-{i:04d}"
    return rows, docs_by_source


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def update_reliability_layer(ledger_count: int, oov_count: int) -> None:
    if not RL_PATH.exists():
        return
    data = json.loads(RL_PATH.read_text(encoding="utf-8"))
    metadata = data.setdefault("metadata", {})
    counts = metadata.setdefault("section_row_counts", {})
    counts["external_source_ledger_csv"] = ledger_count
    counts["lebanese_external_oov_candidates_csv"] = oov_count
    metadata["updated_at_utc"] = now_iso()
    registry = metadata.setdefault("csv_file_registry", {})
    registry["external_source_ledger.csv"] = {
        "path": "data/knowledge_base/arabizi/external_source_ledger.csv",
        "row_count": ledger_count,
        "rule": "External source provenance and license/access gate. Does not imply import permission.",
    }
    registry["lebanese_external_oov_candidates.csv"] = {
        "path": "data/knowledge_base/arabizi/lebanese_external_oov_candidates.csv",
        "row_count": oov_count,
        "rule": "Review-only mined Lebanese OOV surface forms. must_not_auto_promote=true for every row.",
    }
    guardrails = metadata.setdefault("guardrails", [])
    new_guardrail = (
        "External Lebanese OOV candidates are review-only and cannot be promoted "
        "without native review, source permission compatibility, and layer-specific validators."
    )
    if new_guardrail not in guardrails:
        guardrails.append(new_guardrail)
    RL_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_report(ledger_rows: list[dict[str, str]], oov_rows: list[dict[str, str]], docs_by_source: dict[str, int]) -> None:
    layer_counts = Counter(row["suggested_layer"] for row in oov_rows)
    source_token_counts = {
        key: sum(int(row[col]) for row in oov_rows)
        for key, col in {
            "RBZ_LEB_AI_2016": "rbz_identification_count",
            "RBZ_SENZI_AI_2019": "rbz_senzi_ai_count",
            "RBZ_SENZI_SA_2019": "rbz_senzi_sa_count",
            "KAGGLE_RAIDY_CC0_2020": "kaggle_raidy_count",
            "RBZ_SENZI_LEXICON_2019": "rbz_senzi_lexicon_count",
            "RBZ_SENZI_LARGE_2020": "rbz_senzi_large_count",
            "RBZ_THESIS_TRANSLITERATION_2020": "rbz_thesis_translation_count",
        }.items()
    }
    lines = [
        "# Arabizi External Absorption Report",
        "",
        f"Generated: {now_iso()}",
        "",
        "## What Changed",
        "",
        "- Added external source provenance ledger.",
        "- Added Lebanese-priority external OOV candidate queue.",
        "- No external raw text was copied into trusted vocabulary.",
        "- No external row was promoted into production routing vocabulary.",
        "",
        "## Source Documents Mined",
        "",
        "| Source | Documents used | Candidate token hits | License/access note |",
        "|---|---:|---:|---|",
    ]
    ledger_by_id = {row["source_id"]: row for row in ledger_rows}
    for source_id in [
        "RBZ_LEB_AI_2016",
        "RBZ_SENZI_AI_2019",
        "RBZ_SENZI_SA_2019",
        "KAGGLE_RAIDY_CC0_2020",
        "RBZ_SENZI_LEXICON_2019",
        "RBZ_SENZI_LARGE_2020",
        "RBZ_THESIS_TRANSLITERATION_2020",
    ]:
        ledger = ledger_by_id[source_id]
        lines.append(
            f"| {source_id} | {docs_by_source.get(source_id, 0)} | "
            f"{source_token_counts.get(source_id, 0)} | {ledger['license']} |"
        )
    lines.extend(
        [
            "",
            "## Candidate Queue",
            "",
            f"- Rows generated: {len(oov_rows)}",
            f"- All rows have `review_status=PENDING_NATIVE_REVIEW`.",
            f"- All rows have `must_not_auto_promote=true`.",
            "",
            "| Suggested layer | Rows |",
            "|---|---:|",
        ]
    )
    for layer, count in layer_counts.most_common():
        lines.append(f"| {layer} | {count} |")
    lines.extend(
        [
            "",
            "## Top Review-Only Candidates",
            "",
            "| Candidate | Count | Sources | Suggested layer | Risk |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in oov_rows[:25]:
        sources_for_md = row["source_ids"].replace("|", "<br>")
        lines.append(
            f"| `{row['surface_form']}` | {row['observed_count_total']} | "
            f"{sources_for_md} | {row['suggested_layer']} | {row['risk_level']} |"
        )
    lines.extend(
        [
            "",
            "## Required Next Review Actions",
            "",
            "1. Native reviewer triages `lebanese_external_oov_candidates.csv`.",
            "2. Move generic support words into `arabizi_general_word_bank.csv` only after review.",
            "3. Move noise/entities into `arabizi_stoplist.csv` only after review.",
            "4. Move domain issue terms into `arabizi_candidate_bank.csv` only if they map to official CedarFix taxonomy.",
            "5. Re-run all Arabizi validators after any reviewed movement.",
            "",
            "## Citation Notes",
            "",
            "- Project RBZ / SenZi rows are non-commercial research use only and require citation.",
            "- Kaggle Raidy rows are CC0 according to Kaggle metadata, but social text should still be handled sensitively.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ledger_rows = build_ledger()
    oov_rows, docs_by_source = mine_oov_candidates()
    write_csv(LEDGER_PATH, LEDGER_COLUMNS, ledger_rows)
    write_csv(OOV_PATH, OOV_COLUMNS, oov_rows)
    update_reliability_layer(len(ledger_rows), len(oov_rows))
    write_report(ledger_rows, oov_rows, docs_by_source)
    print(f"Wrote {LEDGER_PATH} ({len(ledger_rows)} rows)")
    print(f"Wrote {OOV_PATH} ({len(oov_rows)} rows)")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
