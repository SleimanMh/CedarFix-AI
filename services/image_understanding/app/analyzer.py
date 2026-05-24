"""
Scene analyser for IEP-2: wraps CLIP inference and produces
a structured VisualUnderstandingJSON + image quality assessment.

Phase 1: CLIP zero-shot prompts.
Phase 2: Replace with BLIP-2 captioning + YOLO object detection + Qwen-VL.

AI Engineer 2 owns this file.
"""

from typing import Dict, List, Optional, Tuple

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from cedarfix_shared.schemas import (
    ComplaintType,
    ImageQualityJSON,
    SeverityLevel,
    VisualUnderstandingJSON,
)

# ---------------------------------------------------------------------------
# CLIP zero-shot prompt banks
# ---------------------------------------------------------------------------

# Category prompts — ordered: first N are infrastructure, rest are negatives
_INFRA_PROMPTS: List[Tuple[str, str, str]] = [
    # (prompt_text, visual_category, visual_subcategory)
    ("a photo of road damage or pothole",              "roads",       "pothole"),
    ("a photo of a large hole or crater in the road",  "roads",       "pothole"),
    ("a photo of cracked or broken asphalt",           "roads",       "road_damage"),
    ("a photo of flooding or standing water on street","drainage",    "flooding"),
    ("a photo of garbage or waste piled on street",    "sanitation",  "waste_accumulation"),
    ("a photo of a broken traffic light or signal",    "roads",       "traffic_light"),
    ("a photo of a damaged or cracked sidewalk",       "roads",       "sidewalk_damage"),
    ("a photo of a broken or dark street lamp",        "electricity", "streetlight"),
    ("a photo of a leaking or burst water pipe",       "water",       "pipe_leak"),
    ("a photo of broken infrastructure or utility",    "other",       "other"),
]

_NEGATIVE_PROMPTS = [
    "a random photo unrelated to infrastructure",
    "a selfie or indoor photo",
    "a nature landscape or food photo",
]

_ALL_PROMPTS = [p for p, _, _ in _INFRA_PROMPTS] + _NEGATIVE_PROMPTS
_N_INFRA = len(_INFRA_PROMPTS)

# Objects CLIP can detect via the top matching prompts
_OBJECT_MAP: Dict[str, List[str]] = {
    "pothole":           ["pothole", "road hole", "crater"],
    "road_damage":       ["cracked asphalt", "broken road"],
    "flooding":          ["standing water", "flooded street"],
    "waste_accumulation":["garbage pile", "waste"],
    "traffic_light":     ["broken traffic light"],
    "sidewalk_damage":   ["cracked sidewalk"],
    "streetlight":       ["broken street lamp"],
    "pipe_leak":         ["leaking pipe", "burst pipe"],
    "other":             ["damaged infrastructure"],
}

_SEVERITY_PROMPTS: List[Tuple[str, SeverityLevel]] = [
    ("severe damage completely blocking the road, dangerous flooding, imminent collapse",
     SeverityLevel.CRITICAL),
    ("large pothole or significant road damage, major flooding",
     SeverityLevel.HIGH),
    ("moderate road damage or partial obstruction, noticeable damage",
     SeverityLevel.MEDIUM),
    ("minor crack or small pothole, minimal visible damage",
     SeverityLevel.LOW),
]

# Quality heuristics — minimum image size (px)
_MIN_USABLE_PIXELS = 128 * 128


# ---------------------------------------------------------------------------
# SceneAnalyzer
# ---------------------------------------------------------------------------

class SceneAnalyzer:
    """
    Wraps a loaded CLIP model and produces structured scene understanding.
    Instantiated once inside ImageUnderstandingModel.
    """

    def __init__(self, clip_model: CLIPModel, clip_processor: CLIPProcessor):
        self._model = clip_model
        self._processor = clip_processor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_quality(self, image: Image.Image) -> ImageQualityJSON:
        """Fast heuristic quality check (no ML, sub-millisecond)."""
        issues: List[str] = []
        w, h = image.size
        pixels = w * h
        if pixels < _MIN_USABLE_PIXELS:
            issues.append("image_too_small")
        if image.mode not in ("RGB", "RGBA", "L"):
            issues.append("unsupported_mode")
        # Brightness heuristic: very dark or very bright
        try:
            import numpy as np
            arr = np.array(image.convert("L"), dtype=float)
            mean_brightness = arr.mean()
            if mean_brightness < 20:
                issues.append("too_dark")
            elif mean_brightness > 240:
                issues.append("overexposed")
        except Exception:
            pass
        quality_score = max(0.0, 1.0 - len(issues) * 0.3)
        return ImageQualityJSON(
            usable=len(issues) == 0,
            quality_score=round(quality_score, 2),
            issues=issues,
        )

    def analyze_scene(self, image: Image.Image) -> VisualUnderstandingJSON:
        """
        Run CLIP zero-shot over infrastructure prompts.
        Returns a fully populated VisualUnderstandingJSON.
        """
        # --- Infrastructure category classification ---
        category, subcategory, infra_confidence, top_idx = self._classify_category(image)

        # --- Object list from top matching prompt ---
        detected_objects = _OBJECT_MAP.get(subcategory, ["infrastructure damage"])

        # --- Damage assessment ---
        damage_visible = infra_confidence > 0.35

        # --- Severity ---
        severity = self._estimate_severity(image) if damage_visible else SeverityLevel.LOW

        # --- Caption (rule-based for Phase 1; replace with BLIP-2 in Phase 2) ---
        caption = self._make_caption(subcategory, severity, detected_objects)

        return VisualUnderstandingJSON(
            caption=caption,
            visual_category=category,
            visual_subcategory=subcategory,
            detected_objects=detected_objects,
            damage_visible=damage_visible,
            visual_severity=severity,
            confidence=round(infra_confidence, 3),
        )

    def get_image_embedding(self, image: Image.Image) -> List[float]:
        """Returns L2-normalised 512-dim CLIP image feature."""
        inputs = self._processor(images=image, return_tensors="pt")
        with torch.no_grad():
            vision_out = self._model.vision_model(pixel_values=inputs["pixel_values"])
            features = self._model.visual_projection(vision_out.pooler_output)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features[0].tolist()

    def get_text_embedding(self, text: str) -> List[float]:
        """
        Returns L2-normalised 512-dim CLIP text feature for the given text.

        Because CLIP embeds text and images in the SAME shared space, the
        cosine similarity between this vector and an image embedding produced
        by get_image_embedding() is meaningful without any projection.

        This is the CORRECT approach for intra-complaint alignment.
        The random projection used in fusion.py is only for projecting image
        embeddings into the sentence-transformer text space for fused storage —
        it must NOT be used as an alignment signal.
        """
        inputs = self._processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        )
        with torch.no_grad():
            text_out = self._model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            features = self._model.text_projection(text_out.pooler_output)
            features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features[0].tolist()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clip_probs(self, texts: List[str], image: Image.Image) -> List[float]:
        """Compute CLIP zero-shot probabilities over a list of text prompts."""
        img_inputs = self._processor(images=image, return_tensors="pt")
        txt_inputs = self._processor(
            text=texts, return_tensors="pt", padding=True, truncation=True
        )
        with torch.no_grad():
            vision_out = self._model.vision_model(pixel_values=img_inputs["pixel_values"])
            image_features = self._model.visual_projection(vision_out.pooler_output)
            image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)

            text_out = self._model.text_model(
                input_ids=txt_inputs["input_ids"],
                attention_mask=txt_inputs["attention_mask"],
            )
            text_features = self._model.text_projection(text_out.pooler_output)
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)

            logit_scale = self._model.logit_scale.exp()
            logits = (image_features @ text_features.T) * logit_scale
            probs = logits.softmax(dim=-1)[0].tolist()
        return probs

    def _classify_category(
        self, image: Image.Image
    ) -> Tuple[str, str, float, int]:
        """Returns (category, subcategory, infra_confidence, top_infra_idx)."""
        probs = self._clip_probs(_ALL_PROMPTS, image)
        infra_probs = probs[:_N_INFRA]
        neg_probs = probs[_N_INFRA:]
        infra_total = sum(infra_probs)
        neg_total = sum(neg_probs)
        infra_confidence = infra_total / (infra_total + neg_total + 1e-8)

        top_idx = max(range(_N_INFRA), key=lambda i: infra_probs[i])
        _, cat, sub = _INFRA_PROMPTS[top_idx]
        return cat, sub, infra_confidence, top_idx

    def _estimate_severity(self, image: Image.Image) -> SeverityLevel:
        texts = [p for p, _ in _SEVERITY_PROMPTS]
        probs = self._clip_probs(texts, image)
        best = max(range(len(probs)), key=lambda i: probs[i])
        return _SEVERITY_PROMPTS[best][1]

    @staticmethod
    def _make_caption(
        subcategory: str, severity: SeverityLevel, objects: List[str]
    ) -> str:
        # TODO Phase 2: replace with BLIP-2 generated caption
        obj_str = objects[0] if objects else subcategory.replace("_", " ")
        sev_label = severity.value.lower()
        return f"A {sev_label} severity {obj_str} visible in the image."
