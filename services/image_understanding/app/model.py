"""
Image Understanding Model — CLIP-based structured scene analysis.
AI Engineer 2 owns and improves this file.

Phase 1: CLIP zero-shot + rule-based quality assessment (see analyzer.py).
Phase 2: Replace SceneAnalyzer with BLIP-2 captioning + YOLO detection.
"""

import os
from pathlib import Path

from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from cedarfix_shared.schemas import ImageQualityJSON, ImageUnderstandingResult
from .analyzer import SceneAnalyzer

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/data/uploads")
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")


class ImageUnderstandingModel:
    def __init__(self):
        self.clip_model: CLIPModel = None
        self.clip_processor: CLIPProcessor = None
        self.analyzer: SceneAnalyzer = None

    async def load(self):
        print(f"[IEP-2] Loading CLIP model: {CLIP_MODEL_NAME}")
        self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
        self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
        self.clip_model.eval()
        self.analyzer = SceneAnalyzer(self.clip_model, self.clip_processor)
        print("[IEP-2] CLIP loaded.")

    async def analyze(
        self,
        complaint_id: str,
        image_filename: str,
        complaint_text: str = "",
    ) -> ImageUnderstandingResult:
        """
        Analyse an image.  When `complaint_text` is provided the CLIP text
        encoder is also run, producing `clip_text_embedding` in the same
        512-dim shared CLIP space.  This enables alignment.py to compute
        intra-complaint cosine similarity without any cross-model projection.
        """
        image_path = Path(UPLOADS_DIR) / image_filename

        if not image_path.exists():
            return ImageUnderstandingResult(
                complaint_id=complaint_id,
                image_present=False,
                image_id=image_filename,
            )

        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            return ImageUnderstandingResult(
                complaint_id=complaint_id,
                image_present=False,
                image_id=image_filename,
                image_quality=ImageQualityJSON(
                    usable=False, issues=["unreadable_file"]
                ),
            )

        # 1. Quality check (fast heuristic)
        quality = self.analyzer.assess_quality(image)

        # 2. If unusable, return early with empty visual understanding
        if not quality.usable:
            return ImageUnderstandingResult(
                complaint_id=complaint_id,
                image_present=True,
                image_id=image_filename,
                image_quality=quality,
            )

        # 3. Scene analysis (CLIP zero-shot)
        visual = self.analyzer.analyze_scene(image)

        # 4. Image embedding (512-dim CLIP)
        embedding = self.analyzer.get_image_embedding(image)

        # 5. CLIP text embedding — same 512-dim space as the image embedding.
        #    Direct cosine(clip_text_embedding, image_embedding) is the correct
        #    intra-complaint alignment signal; no projection required.
        clip_text_emb: list = []
        if complaint_text:
            clip_text_emb = self.analyzer.get_text_embedding(complaint_text)

        return ImageUnderstandingResult(
            complaint_id=complaint_id,
            image_present=True,
            image_id=image_filename,
            image_quality=quality,
            visual_understanding=visual,
            image_embedding=embedding,
            clip_text_embedding=clip_text_emb,
        )

