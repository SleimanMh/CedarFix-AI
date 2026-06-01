"""IEP-7 FastAPI application — calibration & drift monitor.

HTTP surface:
- GET /health
- GET /metrics            — Prometheus exposition of calibration gauges
- GET /calibration/latest — most recent per-sector calibration snapshot
- POST /calibration/run   — trigger an on-demand recompute (demo aid)

A background task recomputes calibration on a fixed interval.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Response

from src.iep7.worker import compute_calibration, latest_metrics

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

    _PROM = True
except Exception:  # noqa: BLE001 - degrade if prometheus_client missing
    _PROM = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("iep7")

COMPUTE_INTERVAL_S = int(os.getenv("IEP7_COMPUTE_INTERVAL_S", "600"))

if _PROM:
    ECE_GAUGE = Gauge("cedarfix_calibration_ece", "Expected calibration error", ["sector"])
    BRIER_GAUGE = Gauge("cedarfix_calibration_brier", "Brier score", ["sector"])
    ACC_GAUGE = Gauge("cedarfix_calibration_accuracy", "Routing accuracy", ["sector"])
    N_GAUGE = Gauge("cedarfix_calibration_samples", "Samples per sector", ["sector"])


def _publish_gauges(reports) -> None:
    if not _PROM:
        return
    for report in reports:
        ECE_GAUGE.labels(sector=report.sector).set(report.ece)
        BRIER_GAUGE.labels(sector=report.sector).set(report.brier)
        ACC_GAUGE.labels(sector=report.sector).set(report.accuracy)
        N_GAUGE.labels(sector=report.sector).set(report.n)


async def _compute_loop() -> None:
    while True:
        try:
            reports = await compute_calibration()
            _publish_gauges(reports)
        except Exception as exc:  # noqa: BLE001
            logger.error("IEP-7 compute loop error: %s", exc, exc_info=True)
        try:
            await asyncio.sleep(COMPUTE_INTERVAL_S)
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_compute_loop(), name="iep7-compute")
    logger.info("IEP-7 compute task started (interval=%ss)", COMPUTE_INTERVAL_S)
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("IEP-7 compute task stopped")


app = FastAPI(
    title="CedarFix IEP-7 — Calibration & Drift Monitor",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "service": "iep7", "prometheus": _PROM}


@app.get("/metrics", tags=["ops"])
async def metrics() -> Response:
    if not _PROM:
        return Response("prometheus_client not installed", media_type="text/plain")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/calibration/latest", tags=["calibration"])
async def calibration_latest() -> dict:
    return {"sectors": await latest_metrics()}


@app.post("/calibration/run", tags=["calibration"])
async def calibration_run() -> dict:
    reports = await compute_calibration()
    _publish_gauges(reports)
    return {
        "computed": len(reports),
        "sectors": [
            {"sector": r.sector, "ece": r.ece, "brier": r.brier, "n": r.n}
            for r in reports
        ],
    }
