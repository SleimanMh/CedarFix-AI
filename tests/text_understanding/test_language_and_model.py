from __future__ import annotations

import asyncio

from cedarfix_shared.schemas import TextUnderstandingResult


def test_language_detection_prioritizes_arabizi_then_arabic(import_service_module, monkeypatch):
    detector = import_service_module("text_understanding", "app.language_detector")

    assert detector.detect_language("fi 7afra kbire 3al tari2") == "arabizi"
    assert detector.detect_language("هناك حفرة كبيرة في الطريق") == "ar"

    def unsupported_language(_text):
        return "de"

    monkeypatch.setattr(detector, "detect", unsupported_language)
    assert detector.detect_language("kaputte strasse") == "en"


def test_language_detection_falls_back_to_english_on_detector_error(import_service_module, monkeypatch):
    detector = import_service_module("text_understanding", "app.language_detector")

    def broken(_text):
        raise detector.LangDetectException("too short")

    monkeypatch.setattr(detector, "detect", broken)
    assert detector.detect_language("??") == "en"


class FakeExtractor:
    def __init__(self, *, english_translation):
        self.english_translation = english_translation

    async def extract(self, complaint_id, text, language):
        return TextUnderstandingResult(
            complaint_id=complaint_id,
            original_text=text,
            normalized_text="Route cassee a Hamra",
            language=language,
            english_translation=self.english_translation,
            summary="Broken road in Hamra",
            issue_type="road_damage",
            category="roads",
            subcategory="road_damage",
            confidence=0.9,
        )


class FakeVector(list):
    def tolist(self):
        return list(self)


class FakeEncoder:
    def __init__(self):
        self.encoded_texts = []

    def encode(self, text):
        self.encoded_texts.append(text)
        return FakeVector([0.1, 0.2, 0.3])


def test_text_model_embeds_english_translation_when_available(import_service_module, monkeypatch):
    model_mod = import_service_module("text_understanding", "app.model", ml=True)
    monkeypatch.setattr(model_mod, "detect_language", lambda _text: "fr")
    model = model_mod.TextUnderstandingModel()
    model.extractor = FakeExtractor(english_translation="Broken road in Hamra")
    model.encoder = FakeEncoder()

    result = asyncio.run(model.analyze("c1", "Route cassee a Hamra"))

    assert model.encoder.encoded_texts == ["Broken road in Hamra"]
    assert result.text_embedding == [0.1, 0.2, 0.3]


def test_text_model_falls_back_to_normalized_text_for_embedding(import_service_module, monkeypatch):
    model_mod = import_service_module("text_understanding", "app.model", ml=True)
    monkeypatch.setattr(model_mod, "detect_language", lambda _text: "en")
    model = model_mod.TextUnderstandingModel()
    model.extractor = FakeExtractor(english_translation=None)
    model.encoder = FakeEncoder()

    asyncio.run(model.analyze("c1", "Broken road in Hamra"))

    assert model.encoder.encoded_texts == ["Route cassee a Hamra"]
