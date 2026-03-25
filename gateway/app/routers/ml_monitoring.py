"""ML monitoring router — exposes model health and evaluation metrics."""

import logging

import httpx
from fastapi import APIRouter

from app.config import ML_SERVICE_URL, ML_TIMEOUT_S

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["ml-monitoring"])


@router.get("/status")
async def ml_status():
    """Return ML service health and model loading status."""
    try:
        async with httpx.AsyncClient(timeout=ML_TIMEOUT_S) as client:
            resp = await client.get(f"{ML_SERVICE_URL}/health")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"ML service unreachable: {e}")
        return {"status": "unreachable", "error": str(e)}


@router.get("/metrics")
async def ml_metrics():
    """Return ML model evaluation metrics, feature info, and metadata."""
    try:
        async with httpx.AsyncClient(timeout=ML_TIMEOUT_S) as client:
            resp = await client.get(f"{ML_SERVICE_URL}/model-metrics")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"ML metrics unavailable: {e}")
        return {"error": str(e)}
