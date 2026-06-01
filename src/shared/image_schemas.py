"""IEP-6 multimodal image-hazard contracts and late-fusion rule.

IEP-6 runs a CLIP zero-shot classifier over the citizen-supplied photo and
fuses the visual hazard label with the text-derived routing sector.  The
fusion rule is the concrete realisation of the project's "text + image +
GPS + time" late-fusion novel element: agreement boosts routing
confidence, conflict forces HITL review.

The fusion function is pure and import-safe (no torch needed) so it can be
unit-tested without the vision model installed.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "IMAGE_LABELS",
    "IMAGE_LABEL_TO_SECTOR",
    "FusionDecision",
    "ImageHazardSignal",
    "fuse_image_text",
    "AGREE_BOOST",
    "CONFLICT_PENALTY",
    "MIN_IMAGE_CONFIDENCE",
]

# Visual hazard taxonomy aligned to CedarFix routing sectors.
IMAGE_LABELS: tuple[str, ...] = (
    "a pothole or damaged road surface",
    "a pile of uncollected garbage",
    "a water leak or burst pipe",
    "a flooded street",
    "a sparking or downed electrical wire",
    "a fire or smoke",
    "a fallen tree or debris blocking a road",
    "an ordinary street scene with no hazard",
)

# Map each CLIP prompt to (short_label, routing_sector | None).
IMAGE_LABEL_TO_SECTOR: dict[str, tuple[str, str | None]] = {
    "a pothole or damaged road surface": ("pothole", "ROADS"),
    "a pile of uncollected garbage": ("garbage_pile", "WASTE"),
    "a water leak or burst pipe": ("water_leak", "WATER"),
    "a flooded street": ("flooding", "FLOODING"),
    "a sparking or downed electrical wire": ("sparking_wire", "ELECTRICITY"),
    "a fire or smoke": ("fire", "SAFETY"),
    "a fallen tree or debris blocking a road": ("fallen_tree", "ROADS"),
    "an ordinary street scene with no hazard": ("none", None),
}

# Fusion tuning constants.
AGREE_BOOST: float = 0.10
CONFLICT_PENALTY: float = 0.10
MIN_IMAGE_CONFIDENCE: float = 0.45


class FusionDecision(BaseModel):
    """Outcome of fusing the image hazard label with the text sector."""

    model_config = ConfigDict(extra="forbid")

    agreement: str = Field(..., min_length=1)  # agree | conflict | no_image_signal
    confidence_delta: float = 0.0
    force_hitl: bool = False
    reason: str = Field(default="", max_length=128)


class ImageHazardSignal(BaseModel):
    """Durable IEP-6 packet stored on the complaint."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    image_label: str | None = None
    image_sector: str | None = None
    image_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    model_name: str = "openai/clip-vit-base-patch32"
    fusion: FusionDecision


def fuse_image_text(
    text_sector: str | None,
    image_sector: str | None,
    image_confidence: float | None,
    min_confidence: float = MIN_IMAGE_CONFIDENCE,
) -> FusionDecision:
    """Late-fusion rule between the visual hazard and the text routing sector.

    - No usable image signal  → neutral (no delta, no HITL).
    - Image agrees with text  → boost routing confidence.
    - Image conflicts w/ text → penalise and force HITL review.
    """
    if (
        image_sector is None
        or image_confidence is None
        or image_confidence < min_confidence
    ):
        return FusionDecision(
            agreement="no_image_signal",
            confidence_delta=0.0,
            force_hitl=False,
            reason="image_absent_or_low_confidence",
        )

    text_norm = (text_sector or "").strip().upper()
    image_norm = image_sector.strip().upper()

    if not text_norm or text_norm in {"OTHER", "UNKNOWN"}:
        # Text was uncertain — let the image disambiguate, slight boost only.
        return FusionDecision(
            agreement="image_disambiguates",
            confidence_delta=AGREE_BOOST / 2,
            force_hitl=False,
            reason=f"image_suggests:{image_norm}",
        )

    if text_norm == image_norm:
        return FusionDecision(
            agreement="agree",
            confidence_delta=AGREE_BOOST,
            force_hitl=False,
            reason=f"image_text_agree:{image_norm}",
        )

    return FusionDecision(
        agreement="conflict",
        confidence_delta=-CONFLICT_PENALTY,
        force_hitl=True,
        reason=f"image_text_conflict:text={text_norm},image={image_norm}",
    )
