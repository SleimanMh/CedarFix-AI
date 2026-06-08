"""
IEP-9 — Monitoring + Drift Detection + Retraining Service
===========================================================
Owned by: MLOps Engineer

Responsibilities:
- Expose Prometheus metrics endpoint
- Compute rolling accuracy from admin_corrections
- Detect embedding distribution drift
- Trigger manual retraining via API

DRIFT DETECTION STRATEGY:
  1. Weekly: compute mean routing_confidence from last 7 days vs. prior 7 days
  2. Alert if drop > 10 percentage points
  3. Compute admin correction rate: corrections / total routed
  4. Alert if correction rate > 15%
"""

import os
import time
from fastapi import FastAPI, BackgroundTasks
from prometheus_client import make_asgi_app
from cedarfix_shared.metrics import (
    EMBEDDING_DRIFT_SCORE, ROUTING_ACCURACY_7D, ADMIN_CORRECTION_RATE
)
from .drift import compute_drift_metrics
from .evaluation_judge import (
    PROMPT_VERSION as EVALUATION_PROMPT_VERSION,
    SCHEDULE_ENABLED as EVALUATION_SCHEDULE_ENABLED,
    refresh_evaluation_metrics,
    run_daily_evaluation_once,
    scheduler_loop as evaluation_scheduler_loop,
)
from .retrain import trigger_retraining_job

app = FastAPI(title="IEP-9: Monitoring Service", version="0.1.0")
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "monitoring-service"}


@app.get("/drift/report")
async def drift_report():
    """Return current drift metrics."""
    return await compute_drift_metrics()


@app.post("/retrain/trigger")
async def trigger_retrain(background_tasks: BackgroundTasks, model: str = "all"):
    """
    Manual retraining trigger.
    MLOps Engineer: Wire this to the full retraining pipeline.
    model: "priority" | "routing" | "all"
    """
    background_tasks.add_task(trigger_retraining_job, model)
    return {"status": "retraining_triggered", "model": model}


@app.get("/evaluation/status")
async def evaluation_status():
    """
    Return stored offline judge evaluation aggregates.
    This endpoint is monitoring-only and does not influence live decisions.
    """
    return {
        "status": "ok",
        "prompt_version": EVALUATION_PROMPT_VERSION,
        "scheduler_enabled": EVALUATION_SCHEDULE_ENABLED,
        "metrics": refresh_evaluation_metrics(),
    }


@app.post("/evaluation/run")
async def run_evaluation(
    background_tasks: BackgroundTasks,
    limit: int | None = None,
    complaint_id: str | None = None,
    latest: bool = False,
):
    """
    Manually trigger the offline GPT-4o judge evaluation.
    Intended for ops/research only. Never writes to complaint decision fields.
    """
    background_tasks.add_task(run_daily_evaluation_once, None, limit, complaint_id, latest)
    return {
        "status": "evaluation_triggered",
        "prompt_version": EVALUATION_PROMPT_VERSION,
        "limit": limit,
        "complaint_id": complaint_id,
        "latest": latest,
    }


@app.on_event("startup")
async def startup():
    """Compute initial drift metrics on startup."""
    import asyncio
    asyncio.create_task(_periodic_drift_check())
    if EVALUATION_SCHEDULE_ENABLED:
        asyncio.create_task(evaluation_scheduler_loop())


async def _periodic_drift_check():
    """Check drift every hour and update Prometheus gauges."""
    import asyncio
    while True:
        try:
            report = await compute_drift_metrics()
            EMBEDDING_DRIFT_SCORE.set(report.get("embedding_drift", 0.0))
            ROUTING_ACCURACY_7D.set(report.get("routing_accuracy_7d", 0.0))
            ADMIN_CORRECTION_RATE.set(report.get("admin_correction_rate", 0.0))
            refresh_evaluation_metrics()
        except Exception as e:
            print(f"[IEP-9] Drift check error: {e}")
        await asyncio.sleep(3600)  # Every hour
