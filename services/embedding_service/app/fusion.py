"""
Embedding fusion logic.
AI Engineer 2 owns this. Replace weighted_avg with learned MLP in stretch phase.
"""

import numpy as np
from typing import List, Tuple

TEXT_DIM = int(768)
IMAGE_DIM = int(512)
FUSED_DIM = int(768)

# Linear projection matrix W: IMAGE_DIM → FUSED_DIM (initialized as random unit projection)
# In stretch phase: train this as part of a contrastive learning objective
_W = np.random.randn(IMAGE_DIM, FUSED_DIM).astype(np.float32)
_W = _W / np.linalg.norm(_W, axis=0)


def fuse_embeddings(
    text_emb: List[float],
    image_emb: List[float],
    image_available: bool,
    image_relevance: float = 1.0,
) -> Tuple[List[float], str, float, float]:
    """
    Returns: (fused_vector, strategy_name, text_weight, image_weight)

    If no image: returns text embedding as-is (text_weight=1.0)
    If image available: weighted average after projecting image to 768-dim
    """
    text_arr = np.array(text_emb, dtype=np.float32)
    text_arr = text_arr / (np.linalg.norm(text_arr) + 1e-8)

    if not image_available or not image_emb or len(image_emb) < IMAGE_DIM:
        return text_arr.tolist(), "text_only", 1.0, 0.0

    # Project image embedding to text dimension
    image_arr = np.array(image_emb[:IMAGE_DIM], dtype=np.float32)
    image_arr = image_arr / (np.linalg.norm(image_arr) + 1e-8)
    image_proj = image_arr @ _W  # (512,) @ (512, 768) → (768,)
    image_proj = image_proj / (np.linalg.norm(image_proj) + 1e-8)

    # Weight: more image weight when relevance is high
    # Base: 0.7 text / 0.3 image, scale image weight by relevance
    image_weight = round(0.3 * image_relevance, 3)
    text_weight = round(1.0 - image_weight, 3)

    fused = text_weight * text_arr + image_weight * image_proj
    fused = fused / (np.linalg.norm(fused) + 1e-8)

    return fused.tolist(), "weighted_avg", text_weight, image_weight
