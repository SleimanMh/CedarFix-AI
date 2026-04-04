"""
Prometheus metrics for iep-grid-compatibility service.
Follows the same pattern as the other IEP services.
"""

import time

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── HTTP metrics ──────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["job", "method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["job", "method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# ── Grid compatibility ML metrics ─────────────────────────────────────────────
grid_compat_requests_total = Counter(
    "grid_compat_requests_total",
    "Total /predict calls by predicted compatibility class",
    ["predicted_class"],
)

grid_compat_inference_seconds = Histogram(
    "grid_compat_inference_seconds",
    "End-to-end inference time for both stages (seconds)",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

grid_compat_class_gauge = Gauge(
    "grid_compat_last_predicted_class",
    "Last predicted compatibility class (label dimension)",
    ["compatibility_class"],
)


# ── Middleware ────────────────────────────────────────────────────────────────
class PrometheusMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

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
    app.add_middleware(PrometheusMiddleware, service_name=service_name)
    app.mount("/metrics", make_asgi_app())
