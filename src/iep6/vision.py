"""IEP-6 vision core — CLIP zero-shot hazard classification.

The CLIP model is loaded lazily and cached so that:
- importing this module is cheap and torch-free (unit tests of ``fuse`` work
  without the heavy ML stack installed);
- the first classification pays the model-load cost, subsequent ones reuse it.

If torch / transformers / Pillow are unavailable the classifier degrades
gracefully to ``None`` (no image signal) instead of crashing the pipeline.
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
import threading

from src.shared.image_schemas import (
    IMAGE_LABELS,
    IMAGE_LABEL_TO_SECTOR,
    FusionDecision,
    ImageHazardSignal,
    fuse_image_text,
)

logger = logging.getLogger("iep6.vision")

MODEL_NAME = "openai/clip-vit-base-patch32"

_model = None
_processor = None
_load_lock = threading.Lock()
_load_failed = False


def _ensure_model() -> bool:
    """Lazily load CLIP. Returns True if the model is usable."""
    global _model, _processor, _load_failed
    if _model is not None and _processor is not None:
        return True
    if _load_failed:
        return False
    with _load_lock:
        if _model is not None and _processor is not None:
            return True
        if _load_failed:
            return False
        try:
            import torch  # noqa: F401
            from transformers import CLIPModel, CLIPProcessor

            _model = CLIPModel.from_pretrained(MODEL_NAME)
            _model.eval()
            _processor = CLIPProcessor.from_pretrained(MODEL_NAME)
            logger.info("IEP-6 CLIP model loaded: %s", MODEL_NAME)
            return True
        except Exception as exc:  # noqa: BLE001 - graceful degradation
            logger.warning("IEP-6 CLIP unavailable (%s) — image signal disabled", exc)
            _load_failed = True
            return False


def _decode_image(image_b64: str):
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return None
    try:
        payload = image_b64.split(",", 1)[1] if "," in image_b64 else image_b64
        raw = base64.b64decode(payload, validate=False)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except (binascii.Error, ValueError, OSError) as exc:
        logger.warning("IEP-6 could not decode image: %s", exc)
        return None


def classify_image(image_b64: str) -> tuple[str, str | None, float] | None:
    """Return ``(short_label, sector, confidence)`` or ``None`` if unavailable."""
    if not image_b64 or not _ensure_model():
        return None
    image = _decode_image(image_b64)
    if image is None:
        return None
    try:
        import torch

        prompts = list(IMAGE_LABELS)
        inputs = _processor(
            text=prompts, images=image, return_tensors="pt", padding=True
        )
        with torch.no_grad():
            outputs = _model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0]
        best_index = int(torch.argmax(probs).item())
        confidence = float(probs[best_index].item())
        prompt = prompts[best_index]
        short_label, sector = IMAGE_LABEL_TO_SECTOR[prompt]
        return short_label, sector, confidence
    except Exception as exc:  # noqa: BLE001
        logger.warning("IEP-6 classification failed: %s", exc)
        return None


def analyse(image_b64: str, text_sector: str | None) -> ImageHazardSignal:
    """Classify the image and fuse with the text routing sector."""
    classification = classify_image(image_b64)
    if classification is None:
        return ImageHazardSignal(
            available=False,
            image_label=None,
            image_sector=None,
            image_confidence=None,
            model_name=MODEL_NAME,
            fusion=FusionDecision(
                agreement="no_image_signal",
                confidence_delta=0.0,
                force_hitl=False,
                reason="model_or_image_unavailable",
            ),
        )
    short_label, sector, confidence = classification
    fusion = fuse_image_text(text_sector, sector, confidence)
    return ImageHazardSignal(
        available=True,
        image_label=short_label,
        image_sector=sector,
        image_confidence=confidence,
        model_name=MODEL_NAME,
        fusion=fusion,
    )
