"""
Text Understanding Model — core inference logic.
AI Engineer 1 owns and improves this file.

CURRENT IMPLEMENTATION:
  - Language detection (Arabic / French / English / Arabizi)
  - LLMExtractor: GPT-4o for Arabizi, Qwen2.5 (Ollama) for all other languages
  - Falls back to rule-based StructuredExtractor if both LLMs are unavailable
  - sentence-transformers for 768-dim multilingual embedding
    (encodes the English translation so embedding quality is consistent)
"""

import os
from sentence_transformers import SentenceTransformer

from cedarfix_shared.schemas import TextUnderstandingResult
from .language_detector import detect_language
from .llm_extractor import LLMExtractor


class TextUnderstandingModel:
    def __init__(self):
        self.model_name = os.getenv(
            "MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        )
        self.encoder: SentenceTransformer = None
        self.extractor = LLMExtractor()

    async def load(self):
        print(f"[IEP-1] Loading sentence transformer: {self.model_name}")
        self.encoder = SentenceTransformer(self.model_name)
        print("[IEP-1] Model loaded.")

    async def analyze(self, complaint_id: str, text: str) -> TextUnderstandingResult:
        # 1. Detect language (Arabizi / ar / fr / en)
        language = detect_language(text)
        print(f"[IEP-1] Detected language: {language} for complaint {complaint_id}")

        # 2. LLM extraction + translation to English
        #    GPT-4o is used for Arabizi; Qwen2.5 (Ollama) for everything else.
        result = await self.extractor.extract(complaint_id, text, language)

        # 3. Embed the English text for consistent downstream vector quality.
        #    english_translation is set when language != en; otherwise use normalized_text.
        text_to_embed = result.english_translation or result.normalized_text
        embedding = self.encoder.encode(text_to_embed).tolist()
        result.text_embedding = embedding

        return result

