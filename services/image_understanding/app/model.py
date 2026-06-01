"""
Image Understanding Model — CLIP-based structured scene analysis.
AI Engineer 2 owns and improves this file.

Phase 1: CLIP zero-shot + rule-based quality assessment (see analyzer.py).
Phase 2: Qwen2.5-VL for image reasoning and text-image alignment (VLMAnalyzer).
"""

import logging
import os
from pathlib import Path

from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from cedarfix_shared.schemas import ImageQualityJSON, ImageUnderstandingResult
from .analyzer import SceneAnalyzer, VLMAnalyzer, VLMAlignmentChecker, VLM_ENABLED, VLM_BASE_URL

log = logging.getLogger(__name__)

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/data/uploads")
CLIP_MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "openai/clip-vit-base-patch32")

# CLIP alignment categories where VLM refinement is worthwhile
_VLM_REFINE_ALIGNMENTS = {"UNCERTAIN", "CONTRADICTS", None}


class ImageUnderstandingModel:
    def __init__(self):
        self.clip_model: CLIPModel = None
        self.clip_processor: CLIPProcessor = None
        self.analyzer: SceneAnalyzer = None
        self.vlm_analyzer: VLMAnalyzer = None
        self.vlm_aligner: VLMAlignmentChecker = None

    async def load(self):
        log.info("[IEP-2] Loading CLIP model: %s", CLIP_MODEL_NAME)
        self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
        self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
        self.clip_model.eval()
        self.analyzer = SceneAnalyzer(self.clip_model, self.clip_processor)
        log.info("[IEP-2] CLIP loaded.")

        if VLM_ENABLED and VLM_BASE_URL:
            try:
                self.vlm_analyzer = VLMAnalyzer()
                self.vlm_aligner = VLMAlignmentChecker()
                log.info("[IEP-2] VLM analyzer initialised (model: %s)", os.getenv("VLM_MODEL", "Qwen2.5-VL"))
            except Exception as e:
                log.warning("[IEP-2] VLM init failed — VLM disabled: %s", e)

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

        When VLM is enabled:
          - VLMAnalyzer runs for all valid images → vlm_analysis field populated.
          - VLMAlignmentChecker runs when CLIP alignment is UNCERTAIN or CONTRADICTS.
        """
        # Support both local paths and GCS signed/public URLs
        try:
            if image_filename.startswith("http://") or image_filename.startswith("https://"):
                import httpx
                from io import BytesIO
                resp = httpx.get(image_filename, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                image = Image.open(BytesIO(resp.content)).convert("RGB")
            else:
                image_path = Path(UPLOADS_DIR) / image_filename
                if not image_path.exists():
                    return ImageUnderstandingResult(
                        complaint_id=complaint_id,
                        image_present=False,
                        image_id=image_filename,
                    )
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

        # 5. VLM Phase 2 — richer semantic analysis (async, non-blocking on CLIP path)
        vlm_analysis = None
        if self.vlm_analyzer:
            # Primary image understanding must remain image-only. Text is used
            # later by the dedicated alignment checker, not to bias labels.
            vlm_analysis = await self.vlm_analyzer.analyze(image, None)

            # Prefer VLM labels/caption when available so downstream UI and matching
            # reflect the richer model output (especially for issue_type=other cases).
            if vlm_analysis:
                visual = visual.model_copy(update={
                    "caption": vlm_analysis.caption or visual.caption,
                    "visual_category": vlm_analysis.visual_category or visual.visual_category,
                    "visual_subcategory": vlm_analysis.visual_subcategory or visual.visual_subcategory,
                    "damage_visible": vlm_analysis.damage_visible,
                    "confidence": float(vlm_analysis.confidence),
                    "semantic_domain": vlm_analysis.semantic_domain or visual.semantic_domain,
                    "physical_component": vlm_analysis.physical_component or visual.physical_component,
                    "failure_mode": vlm_analysis.failure_mode or visual.failure_mode,
                    "visual_candidates": vlm_analysis.visual_candidates,
                })

            # If VLM ran: update alignment when CLIP was uncertain and VLM gives high confidence
            if vlm_analysis and self.vlm_aligner and complaint_text:
                # Determine CLIP alignment from the result (set by alignment.py after embedding)
                # We check here too to avoid an unnecessary VLM call
                clip_alignment = None  # alignment.py fills this in after fusion; pre-check skipped
                vlm_align_data = await self.vlm_aligner.check_alignment(
                    image, complaint_text, clip_alignment or "UNCERTAIN"
                )
                if vlm_align_data:
                    vlm_analysis = vlm_analysis.model_copy(update={
                        "vlm_alignment": vlm_align_data.get("alignment"),
                        "vlm_alignment_confidence": vlm_align_data.get("confidence"),
                    })

        # 6. CLIP text embedding — same 512-dim space as the image embedding.
        #    If VLM produced a caption, use it as the image-side text signal for
        #    alignment. Otherwise fall back to a CLIP-friendly prompt by subcategory.
        _SUBCAT_TO_CLIP_PROMPT = {
            "pothole":            "a photo of road damage or pothole",
            "road_damage":        "a photo of cracked or broken road surface",
            "flooding":           "a photo of street flooding or standing water",
            "waste_accumulation": "a photo of garbage or waste accumulation on the street",
            "outage":             "a photo of electricity or power outage, dark street",
            "traffic_light":      "a photo of a broken or non-functioning traffic light",
            "pipe_leak":          "a photo of a burst or leaking water pipe",
            "sidewalk_damage":    "a photo of a cracked or broken sidewalk",
            "streetlight":        "a photo of a broken or dark street lamp",
            "other":              "a photo of public infrastructure damage",
        }
        clip_text_emb: list = []
        if complaint_text:
            vlm_caption = (vlm_analysis.caption if vlm_analysis else "") or ""
            if vlm_caption.strip():
                clip_prompt = vlm_caption.strip()
            else:
                detected_subcat = visual.visual_subcategory if visual else "other"
                clip_prompt = _SUBCAT_TO_CLIP_PROMPT.get(
                    detected_subcat,
                    f"a photo of {detected_subcat.replace('_', ' ')}",
                )
            clip_text_emb = self.analyzer.get_text_embedding(clip_prompt)

        return ImageUnderstandingResult(
            complaint_id=complaint_id,
            image_present=True,
            image_id=image_filename,
            image_quality=quality,
            visual_understanding=visual,
            image_embedding=embedding,
            clip_text_embedding=clip_text_emb,
            vlm_analysis=vlm_analysis,
        )

