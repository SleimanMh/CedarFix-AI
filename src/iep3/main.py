"""IEP-3 FastAPI application.

HTTP surface: health probe only.
The real work happens in the Redis Streams worker launched at startup.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.iep3.worker import run_worker
from src.shared import metrics as M

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("iep3")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(run_worker(), name="iep3-worker")
    logger.info("IEP-3 worker task started")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("IEP-3 worker task stopped")


app = FastAPI(
    title="CedarFix IEP-3 — Calibrated Routing & Priority",
    version="0.1.0",
    lifespan=lifespan,
)

M.add_metrics_route(app, "iep3")


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "iep3"}
