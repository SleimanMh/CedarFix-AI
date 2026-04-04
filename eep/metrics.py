"""
Shared Prometheus metrics for the EV Charging Platform.
Each service imports this module and calls setup_metrics(app, service_name).

Usage:
    from metrics import setup_metrics
    setup_metrics(app, "iep-forecast")
"""

from prometheus_client import (
    Counter, Histogram, Gauge,
    make_asgi_app,
)
from fastapi import FastAPI
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── HTTP metrics (per service) ────────────────────────────────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["job", "method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["job", "method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── ML-specific metrics ───────────────────────────────────────────────────────

# Forecast service
ev_forecast_predicted_kw = Gauge(
    "ev_forecast_predicted_kw_avg",
    "Average predicted kW from last forecast call",
)
ev_forecast_confidence_width = Gauge(
    "ev_forecast_confidence_width_avg",
    "Average CI width (upper - lower) from last forecast call",
)
ev_forecast_n_slots = Gauge(
    "ev_forecast_n_slots",
    "Number of slots in last forecast request",
)

# Optimizer service
ev_optimizer_solves_total = Counter(
    "ev_optimizer_solves_total",
    "Total optimizer solve calls",
    ["status"],  # optimal, greedy_fallback, infeasible
)
ev_optimizer_solve_time_seconds = Histogram(
    "ev_optimizer_solve_time_seconds",
    "Optimizer solve time in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)
ev_optimizer_sessions_gauge = Gauge(
    "ev_optimizer_sessions_active",
    "Number of EV sessions in last optimize call",
)
ev_optimizer_transformer_peak_kw = Gauge(
    "ev_optimizer_transformer_peak_kw",
    "Transformer peak load from last optimize call (kW)",
)

# Governance service
ev_governance_mae_kw = Gauge(
    "ev_governance_mae_kw",
    "Rolling forecast MAE in kW",
)
ev_governance_mae_baseline_kw = Gauge(
    "ev_governance_mae_baseline_kw",
    "Baseline forecast MAE in kW",
)
ev_governance_psi = Gauge(
    "ev_governance_psi",
    "Population Stability Index (drift signal)",
)
ev_governance_drift_detected = Gauge(
    "ev_governance_drift_detected",
    "1 if drift detected, 0 otherwise",
)
ev_governance_retrain_recommended = Gauge(
    "ev_governance_retrain_recommended",
    "1 if retraining is recommended, 0 otherwise",
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records http_requests_total and http_request_duration_seconds."""

    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Skip /metrics endpoint itself
        if request.url.path == "/metrics":
            return response

        http_requests_total.labels(
            job=self.service_name,
            method=request.method,
            endpoint=request.url.path,
            status=str(response.status_code),
        ).inc()

        http_request_duration_seconds.labels(
            job=self.service_name,
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)

        return response


def setup_metrics(app: FastAPI, service_name: str) -> None:
    """
    Mount /metrics endpoint and add request instrumentation middleware.
    Call this once at module level after creating your FastAPI app.
    """
    app.add_middleware(PrometheusMiddleware, service_name=service_name)
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
