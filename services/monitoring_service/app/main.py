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

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from prometheus_client import make_asgi_app
from cedarfix_shared.metrics import (
    EMBEDDING_DRIFT_SCORE, ROUTING_ACCURACY_7D, ADMIN_CORRECTION_RATE
)
from .drift import compute_drift_metrics
from .retrain import trigger_retraining_job


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run periodic drift monitoring while the service is alive."""
    task = asyncio.create_task(_periodic_drift_check())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="IEP-9: Monitoring Service", version="0.1.0", lifespan=lifespan)
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


async def _periodic_drift_check():
    """Check drift every hour and update Prometheus gauges."""
    while True:
        try:
            report = await compute_drift_metrics()
            EMBEDDING_DRIFT_SCORE.set(report.get("embedding_drift", 0.0))
            ROUTING_ACCURACY_7D.set(report.get("routing_accuracy_7d", 0.0))
            ADMIN_CORRECTION_RATE.set(report.get("admin_correction_rate", 0.0))
        except Exception as e:
            print(f"[IEP-9] Drift check error: {e}")
        await asyncio.sleep(3600)  # Every hour
