"""IEP-6 FastAPI application — multimodal image-hazard fusion service."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from src.iep6.vision import analyse
from src.iep6.worker import run_worker
from src.shared import metrics as M

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("iep6")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(run_worker(), name="iep6-worker")
    logger.info("IEP-6 worker task started")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("IEP-6 worker task stopped")


app = FastAPI(
    title="CedarFix IEP-6 — Multimodal Image-Hazard Fusion",
    version="0.1.0",
    lifespan=lifespan,
)

M.add_metrics_route(app, "iep6")


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_b64: str
    text_sector: str | None = None


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "iep6"}


@app.post("/classify", tags=["vision"])
async def classify(body: ClassifyRequest) -> dict:
    """On-demand classification + fusion (used for demos / ad-hoc checks)."""
    signal = await asyncio.to_thread(analyse, body.image_b64, body.text_sector)
    return signal.model_dump()
