"""
IEP-2 — Image Understanding Service
======================================
Owned by: AI Engineer 2 (Vision/Multimodal)

Responsibilities:
- Load and validate uploaded images
- Run CLIP to produce 512-dim image embedding
- Score image relevance to infrastructure complaints
- Estimate visual severity signal
- Optionally detect objects with DETR

MODEL: openai/clip-vit-base-patch32
  - Shared text-image embedding space
  - Critical for multimodal fusion in IEP-3
  - Runs on CPU, ~350ms per image

DATA NEEDED FOR THIS SERVICE:
  - Infrastructure damage images with severity labels
  - Negative examples (unrelated images to train relevance filter)
  - At minimum 50 real images to validate CLIP zero-shot performance
"""

import time
from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import make_asgi_app
from cedarfix_shared.schemas import ImageUnderstandingResult
from cedarfix_shared.metrics import IMAGE_ANALYSIS_DURATION, IMAGE_RELEVANCE
from .model import ImageUnderstandingModel

app = FastAPI(title="IEP-2: Image Understanding", version="0.2.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

model: ImageUnderstandingModel = None


@app.on_event("startup")
async def load_models():
    global model
    model = ImageUnderstandingModel()
    await model.load()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "image-understanding", "model_loaded": model is not None}


class ImageAnalysisRequest(BaseModel):
    complaint_id: str
    image_filename: str
    # Optional: the complaint text.  When provided, IEP-2 also runs the CLIP
    # text encoder to produce clip_text_embedding (512-dim, shared CLIP space).
    # alignment.py uses this for intra-complaint alignment without projection.
    complaint_text: str = ""


@app.post("/analyze", response_model=ImageUnderstandingResult)
async def analyze_image(request: ImageAnalysisRequest):
    start = time.time()
    result = await model.analyze(
        request.complaint_id,
        request.image_filename,
        request.complaint_text,
    )
    elapsed_ms = int((time.time() - start) * 1000)
    result.processing_ms = elapsed_ms
    IMAGE_ANALYSIS_DURATION.observe(elapsed_ms / 1000)
    relevance = result.visual_understanding.confidence if result.image_present else 0.0
    IMAGE_RELEVANCE.observe(relevance)
    return result
