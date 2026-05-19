"""
Text Understanding Model — core inference logic.
AI Engineer 1 owns and improves this file.

DATA NEEDED FOR THIS SERVICE:
  - Labeled complaint texts in Arabic, French, English
  - complaint_type labels (pothole, flooding, etc.)
  - Named location annotations (Hamra, Cola, Jounieh, etc.)
  - Min 200 examples per complaint type for fine-tuning

CURRENT IMPLEMENTATION: 
  - Keyword-based complaint type classification (replace with fine-tuned classifier)
  - langdetect for language detection
  - sentence-transformers for embedding
  - Rule-based entity extraction (replace with NER model)
"""

import re
from typing import List, Tuple
from langdetect import detect, LangDetectException
from sentence_transformers import SentenceTransformer
from cedarfix_shared.schemas import TextAnalysisResult, Language, ComplaintType
import os


# ---------------------------------------------------------------------------
# Keyword maps — Replace this with a trained classifier in Phase 3
# ---------------------------------------------------------------------------

COMPLAINT_TYPE_KEYWORDS = {
    ComplaintType.POTHOLE: [
        "pothole", "hole", "pit", "حفرة", "تلف الطريق", "nid de poule", "trou",
    ],
    ComplaintType.FLOODING: [
        "flood", "water", "inundation", "فيضان", "مياه", "غمر", "inondation", "eau",
    ],
    ComplaintType.ELECTRICITY: [
        "electricity", "power", "outage", "كهرباء", "انقطاع", "électricité", "panne",
    ],
    ComplaintType.TRAFFIC_LIGHT: [
        "traffic light", "signal", "إشارة", "إشارة المرور", "feu rouge", "feu de signalisation",
    ],
    ComplaintType.WASTE: [
        "waste", "garbage", "trash", "نفايات", "قمامة", "déchets", "ordures",
    ],
    ComplaintType.ROAD_DAMAGE: [
        "road damage", "crack", "broken road", "طريق", "تشقق", "route endommagée",
    ],
    ComplaintType.STREETLIGHT: [
        "streetlight", "lamp", "lighting", "إنارة", "مصباح", "éclairage", "lampadaire",
    ],
    ComplaintType.WATER_PIPE: [
        "pipe", "leak", "water pipe", "أنابيب", "تسرب", "fuite d'eau",
    ],
    ComplaintType.SIDEWALK: [
        "sidewalk", "pavement", "ramp", "رصيف", "trottoir",
    ],
}

LOCATION_PATTERNS = [
    r'\b(hamra|cola|jounieh|tripoli|sidon|tyre|baabda|ashrafieh|verdun|bourj hammoud|'
    r'dekwaneh|sin el fil|jdeideh|antelias|dbayeh|kaslik|jbeil|byblos|'
    r'الحمراء|كولا|جونيه|طرابلس|صيدا|صور|الأشرفية|بعبدا|عبدة)\b',
]


class TextUnderstandingModel:
    def __init__(self):
        self.model_name = os.getenv(
            "MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )
        self.encoder = None

    async def load(self):
        print(f"[IEP-1] Loading sentence transformer: {self.model_name}")
        self.encoder = SentenceTransformer(self.model_name)
        print("[IEP-1] Model loaded.")

    async def analyze(self, complaint_id: str, text: str) -> TextAnalysisResult:
        # 1. Language detection
        lang = self._detect_language(text)

        # 2. Normalize text
        normalized = self._normalize(text)

        # 3. Classify complaint type
        complaint_type, type_confidence = self._classify_type(normalized)

        # 4. Extract keywords
        keywords = self._extract_keywords(normalized, complaint_type)

        # 5. Extract location mentions
        location_mentions = self._extract_locations(normalized)

        # 6. Produce embedding
        embedding = self.encoder.encode(normalized).tolist()

        return TextAnalysisResult(
            complaint_id=complaint_id,
            detected_language=lang,
            normalized_text=normalized,
            complaint_type=complaint_type,
            complaint_type_confidence=type_confidence,
            extracted_keywords=keywords,
            location_mentions=location_mentions,
            text_embedding=embedding,
            analysis_confidence=type_confidence,
            processing_ms=0,  # Set by caller
        )

    def _detect_language(self, text: str) -> Language:
        try:
            detected = detect(text)
            if detected == "ar":
                return Language.ARABIC
            elif detected == "fr":
                return Language.FRENCH
            elif detected == "en":
                return Language.ENGLISH
            return Language.UNKNOWN
        except LangDetectException:
            return Language.UNKNOWN

    def _normalize(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _classify_type(self, text: str) -> Tuple[ComplaintType, float]:
        """
        Keyword-based classification. 
        TODO (AI Engineer 1): Replace with fine-tuned multilingual classifier.
        Training data needed: labeled complaints with complaint_type per language.
        """
        text_lower = text.lower()
        scores = {}
        for ctype, keywords in COMPLAINT_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > 0:
                scores[ctype] = score

        if not scores:
            return ComplaintType.OTHER, 0.4

        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = min(scores[best] / total + 0.1, 0.95)
        return best, round(confidence, 3)

    def _extract_keywords(self, text: str, complaint_type: ComplaintType) -> List[str]:
        keywords = set()
        for kw in COMPLAINT_TYPE_KEYWORDS.get(complaint_type, []):
            if kw.lower() in text.lower():
                keywords.add(kw)
        return list(keywords)[:10]

    def _extract_locations(self, text: str) -> List[str]:
        """
        Regex-based location extraction.
        TODO (AI Engineer 1): Replace with CAMeL-Lab Arabic NER model.
        """
        mentions = []
        for pattern in LOCATION_PATTERNS:
            found = re.findall(pattern, text, re.IGNORECASE)
            mentions.extend(found)
        return list(set(mentions))
