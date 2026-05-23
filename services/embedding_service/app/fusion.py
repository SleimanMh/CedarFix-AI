"""
Embedding fusion for IEP-3.

Fuses a 768-dim text embedding and a 512-dim image embedding into a
single 768-dim vector stored in Qdrant (fused_embeddings collection).

─────────────────────────────────────────────────────────────
SCOPE OF THE RANDOM PROJECTION
─────────────────────────────────────────────────────────────
The random projection matrix W (512 → 768) defined below is used ONLY
to produce the fused vector for Qdrant storage and backward-compatible
retrieval.  It is NOT a semantically valid cross-model bridge.

Do NOT use project_image_embedding() as an alignment signal between text
and image.  CLIP already embeds images and text prompts in the same 512-dim
space; use cosine(clip_text_embedding, image_embedding) directly in
alignment.py when clip_text_embedding is available.

The random projection's purpose is purely dimensional:
  sentence-transformer text embedding  →  768-dim
  CLIP image embedding                 →  512-dim  (projected to 768 for storage)
  weighted average                     →  768-dim fused vector for Qdrant

TODO (Phase 2): replace W with a trained contrastive MLP projection head
that genuinely aligns the two embedding spaces.
─────────────────────────────────────────────────────────────

The random projection matrix W is initialised once at import time with a
fixed seed so the same projection is used across all service restarts.
"""

import numpy as np
from typing import List, Tuple

TEXT_DIM = 768
IMAGE_DIM = 512
FUSED_DIM = 768

# Fixed seed → deterministic projection across restarts
_rng = np.random.default_rng(seed=42)
_W = _rng.standard_normal((IMAGE_DIM, FUSED_DIM)).astype(np.float32)
_W = _W / (np.linalg.norm(_W, axis=0) + 1e-8)


def project_image_embedding(image_emb: List[float]) -> List[float]:
    """
    Project a 512-dim CLIP image vector into the 768-dim text embedding space.
    Used by both fusion and alignment modules.
    """
    arr = np.array(image_emb[:IMAGE_DIM], dtype=np.float32)
    arr = arr / (np.linalg.norm(arr) + 1e-8)
    proj = arr @ _W
    proj = proj / (np.linalg.norm(proj) + 1e-8)
    return proj.tolist()


def fuse_embeddings(
    text_emb: List[float],
    image_emb: List[float],
    image_available: bool,
    image_relevance: float = 1.0,
) -> Tuple[List[float], str, float, float]:
    """
    Returns (fused_vector, strategy, text_weight, image_weight).

    Strategy:
      text_only    — no usable image
      weighted_avg — image available; image_weight = 0.3 × image_relevance
    """
    text_arr = np.array(text_emb, dtype=np.float32)
    text_arr = text_arr / (np.linalg.norm(text_arr) + 1e-8)

    if not image_available or not image_emb or len(image_emb) < IMAGE_DIM:
        return text_arr.tolist(), "text_only", 1.0, 0.0

    image_proj = np.array(project_image_embedding(image_emb), dtype=np.float32)
    image_weight = round(float(np.clip(0.3 * image_relevance, 0.0, 0.4)), 3)
    text_weight = round(1.0 - image_weight, 3)

    fused = text_weight * text_arr + image_weight * image_proj
    fused = fused / (np.linalg.norm(fused) + 1e-8)
    return fused.tolist(), "weighted_avg", text_weight, image_weight
