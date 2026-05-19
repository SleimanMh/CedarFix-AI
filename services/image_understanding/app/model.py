"""
Image Understanding Model — CLIP-based zero-shot analysis.
AI Engineer 2 owns and improves this file.
"""

import os
from pathlib import Path
from typing import List, Tuple

import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from cedarfix_shared.schemas import ImageAnalysisResult, SeverityLevel

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/data/uploads")
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")

# Zero-shot text prompts for relevance scoring
RELEVANCE_PROMPTS = [
    "a photo of road damage or pothole",
    "a photo of flooding or standing water on a street",
    "a photo of broken infrastructure",
    "a photo of garbage or waste on the street",
    "a photo of a broken traffic light",
    "a photo of damaged sidewalk",
    "a photo of a broken streetlight",
    "a photo of a water pipe leak",
    "a random unrelated photo",
    "a selfie or indoor photo",
]

SEVERITY_PROMPTS = {
    SeverityLevel.CRITICAL: "severe damage completely blocking the road, dangerous flooding",
    SeverityLevel.HIGH: "large pothole or significant road damage, major flooding",
    SeverityLevel.MEDIUM: "moderate road damage or partial obstruction",
    SeverityLevel.LOW: "minor crack or small pothole, minimal damage",
}


class ImageUnderstandingModel:
    def __init__(self):
        self.clip_model = None
        self.clip_processor = None

    async def load(self):
        print(f"[IEP-2] Loading CLIP model: {CLIP_MODEL_NAME}")
        self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
        self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
        self.clip_model.eval()
        print("[IEP-2] CLIP loaded.")

    async def analyze(self, complaint_id: str, image_filename: str) -> ImageAnalysisResult:
        image_path = Path(UPLOADS_DIR) / image_filename

        if not image_path.exists():
            return ImageAnalysisResult(
                complaint_id=complaint_id,
                image_available=False,
                processing_ms=0,
            )

        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            return ImageAnalysisResult(
                complaint_id=complaint_id,
                image_available=False,
                processing_ms=0,
            )

        # 1. Get image embedding
        image_embedding = self._get_image_embedding(image)

        # 2. Score relevance (zero-shot)
        relevance_score, detected_objects = self._score_relevance(image)

        # 3. Estimate visual severity
        visual_severity = self._estimate_severity(image) if relevance_score > 0.3 else SeverityLevel.LOW

        # 4. Generate scene description
        scene_description = self._describe_scene(detected_objects, visual_severity)

        return ImageAnalysisResult(
            complaint_id=complaint_id,
            image_available=True,
            detected_objects=detected_objects,
            scene_description=scene_description,
            visual_severity_signal=visual_severity,
            image_embedding=image_embedding,
            image_relevance_score=relevance_score,
            analysis_confidence=relevance_score,
            processing_ms=0,
        )

    def _get_image_embedding(self, image: Image.Image) -> List[float]:
        inputs = self.clip_processor(images=image, return_tensors="pt")
        with torch.no_grad():
            features = self.clip_model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
        return features[0].tolist()

    def _score_relevance(self, image: Image.Image) -> Tuple[float, List[str]]:
        """
        Use CLIP zero-shot to find which prompts match the image.
        The first 8 prompts are infrastructure-related; last 2 are negative.
        """
        inputs = self.clip_processor(
            text=RELEVANCE_PROMPTS,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = self.clip_model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()

        infrastructure_score = sum(probs[:8])
        negative_score = sum(probs[8:])
        relevance = infrastructure_score / (infrastructure_score + negative_score + 1e-8)

        # Detect objects from top matching prompts
        top_indices = sorted(range(len(probs[:8])), key=lambda i: probs[i], reverse=True)[:3]
        detected = [RELEVANCE_PROMPTS[i].replace("a photo of ", "") for i in top_indices if probs[i] > 0.05]

        return round(relevance, 3), detected

    def _estimate_severity(self, image: Image.Image) -> SeverityLevel:
        severity_texts = list(SEVERITY_PROMPTS.values())
        severity_levels = list(SEVERITY_PROMPTS.keys())

        inputs = self.clip_processor(
            text=severity_texts,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = self.clip_model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()

        best_idx = probs.index(max(probs))
        return severity_levels[best_idx]

    def _describe_scene(self, objects: List[str], severity: SeverityLevel) -> str:
        if not objects:
            return "Infrastructure issue detected."
        primary = objects[0] if objects else "damage"
        return f"{severity.value} severity: {primary}."
