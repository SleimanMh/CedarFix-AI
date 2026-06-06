from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from cedarfix_shared.schemas import (
    ImageQualityJSON,
    SeverityLevel,
    VisualIssueCandidate,
    VisualUnderstandingJSON,
    VLMImageAnalysis,
)


def _png_bytes(color="red"):
    buf = BytesIO()
    Image.new("RGB", (128, 128), color).save(buf, format="PNG")
    return buf.getvalue()


def test_image_model_returns_unreadable_result_when_storage_read_fails(import_service_module, monkeypatch):
    model_mod = import_service_module("image_understanding", "app.model", ml=True)
    monkeypatch.setattr(model_mod, "read_image_bytes", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")))
    model = model_mod.ImageUnderstandingModel()

    result = asyncio.run(model.analyze("c1", "local://missing.jpg"))

    assert result.image_present is False
    assert result.image_quality.usable is False
    assert result.image_quality.issues == ["unreadable_file"]


class UnusableAnalyzer:
    def __init__(self):
        self.scene_called = False

    def assess_quality(self, _image):
        return ImageQualityJSON(usable=False, quality_score=0.4, issues=["too_dark"])

    def analyze_scene(self, _image):
        self.scene_called = True
        raise AssertionError("scene analysis should be skipped")


def test_image_model_returns_early_for_unusable_images(import_service_module, monkeypatch):
    model_mod = import_service_module("image_understanding", "app.model", ml=True)
    monkeypatch.setattr(model_mod, "read_image_bytes", lambda *_args, **_kwargs: _png_bytes("black"))
    model = model_mod.ImageUnderstandingModel()
    model.analyzer = UnusableAnalyzer()

    result = asyncio.run(model.analyze("c1", "local://dark.png"))

    assert result.image_present is True
    assert result.image_quality.issues == ["too_dark"]
    assert model.analyzer.scene_called is False
    assert result.image_embedding == []


class Analyzer:
    def __init__(self):
        self.text_inputs = []

    def assess_quality(self, _image):
        return ImageQualityJSON(usable=True, quality_score=0.95)

    def analyze_scene(self, _image):
        return VisualUnderstandingJSON(
            caption="A damaged road surface.",
            visual_category="roads",
            visual_subcategory="road_damage",
            damage_visible=True,
            visual_severity=SeverityLevel.MEDIUM,
            confidence=0.62,
            semantic_domain="transportation",
            physical_component="road_surface",
            failure_mode="damage",
        )

    def get_image_embedding(self, _image):
        return [0.1, 0.2, 0.3]

    def get_text_embedding(self, text):
        self.text_inputs.append(text)
        return [0.4, 0.5, 0.6]


class VLMAnalyzer:
    async def analyze(self, _image, text):
        assert text is None
        return VLMImageAnalysis(
            image_type="infrastructure_damage",
            is_valid_complaint_image=True,
            damage_visible=True,
            visual_category="utilities",
            visual_subcategory="low_hanging_power_line",
            caption="A low hanging power line crosses the road.",
            damage_severity=SeverityLevel.HIGH,
            confidence=0.91,
            semantic_domain="utilities",
            physical_component="power_line",
            failure_mode="low_hanging",
            visual_candidates=[
                VisualIssueCandidate(
                    visual_category="utilities",
                    visual_subcategory="low_hanging_power_line",
                    semantic_domain="utilities",
                    physical_component="power_line",
                    failure_mode="low_hanging",
                    confidence=0.91,
                )
            ],
        )


class VLMAligner:
    async def check_alignment(self, _image, text, clip_alignment):
        assert "wire" in text
        assert clip_alignment == "UNCERTAIN"
        return {"alignment": "confirms", "confidence": 0.87}


def test_image_model_success_path_applies_vlm_refinement_and_text_embedding(import_service_module, monkeypatch):
    model_mod = import_service_module("image_understanding", "app.model", ml=True)
    monkeypatch.setattr(model_mod, "read_image_bytes", lambda *_args, **_kwargs: _png_bytes())
    model = model_mod.ImageUnderstandingModel()
    model.analyzer = Analyzer()
    model.vlm_analyzer = VLMAnalyzer()
    model.vlm_aligner = VLMAligner()

    result = asyncio.run(model.analyze("c1", "local://wire.png", complaint_text="Low wire over the road"))

    assert result.image_present is True
    assert result.image_embedding == [0.1, 0.2, 0.3]
    assert result.clip_text_embedding == [0.4, 0.5, 0.6]
    assert model.analyzer.text_inputs == ["Low wire over the road"]
    assert result.visual_understanding.visual_category == "utilities"
    assert result.visual_understanding.visual_subcategory == "low_hanging_power_line"
    assert result.visual_understanding.confidence == 0.91
    assert result.vlm_analysis.vlm_alignment == "confirms"
    assert result.vlm_analysis.vlm_alignment_confidence == 0.87
