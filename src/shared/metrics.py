"""Central Prometheus metric definitions for all CedarFix services.

This module is the single source of truth for the metrics documented in
``docs/MONITORING_SIGNALS.md``. Importing it is safe even when
``prometheus_client`` is not installed: every metric degrades to a no-op stub
and ``/metrics`` returns a clear, non-fatal message.

Each service runs in its own process and therefore exposes only the metrics it
actually observes; Prometheus aggregates across jobs. Metric names and label
sets here MUST stay in sync with ``docs/MONITORING_SIGNALS.md``.
"""
from __future__ import annotations

from fastapi import FastAPI, Response

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except Exception:  # noqa: BLE001 - degrade gracefully if dependency missing
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _Noop:  # pragma: no cover - exercised only when dep is absent
        def __init__(self, *args, **kwargs) -> None: ...

        def labels(self, *args, **kwargs) -> "_Noop":
            return self

        def inc(self, *args, **kwargs) -> None: ...

        def set(self, *args, **kwargs) -> None: ...

        def observe(self, *args, **kwargs) -> None: ...

    Counter = Gauge = Histogram = _Noop  # type: ignore[assignment,misc]

    def generate_latest(*args, **kwargs) -> bytes:  # type: ignore[misc]
        return b""


# ── Core pipeline metrics ─────────────────────────────────────────────────────
COMPLAINTS_RECEIVED = Counter(
    "cedarfix_complaints_received_total",
    "Total complaints submitted to EEP",
    ["source"],
)
COMPLAINTS_PROCESSED = Counter(
    "cedarfix_complaints_processed_total",
    "Complaints reaching a terminal state",
    ["sector", "state"],
)
HITL_REQUIRED = Counter(
    "cedarfix_hitl_required_total",
    "Complaints escalated to human review",
    ["sector", "reason"],
)
PIPELINE_LATENCY = Histogram(
    "cedarfix_pipeline_latency_seconds",
    "Per-stage processing latency",
    ["stage"],
)

# ── IEP-1 language signal ─────────────────────────────────────────────────────
IEP1_DRIFT_SCORE = Histogram(
    "cedarfix_iep1_drift_score",
    "Distribution of language drift scores (0-3)",
    ["language"],
    buckets=(0, 1, 2, 3),
)
OOV_TOKEN_RATE = Gauge(
    "cedarfix_oov_token_rate",
    "Most recent fraction of out-of-vocabulary tokens",
    ["risk_level"],
)

# ── IEP-2 deduplication ───────────────────────────────────────────────────────
IEP2_DUPLICATE_RATE = Gauge(
    "cedarfix_iep2_duplicate_rate",
    "Rolling fraction of incoming reports classified as duplicates",
    ["sector"],
)
IEP2_CLUSTER_SIZE = Histogram(
    "cedarfix_iep2_cluster_size",
    "Distribution of incident cluster sizes",
    ["sector"],
)

# ── IEP-3 routing ─────────────────────────────────────────────────────────────
ROUTING_CONFIDENCE = Histogram(
    "cedarfix_routing_confidence",
    "Distribution of routing confidence scores",
    ["sector"],
)
IEP3_PRIORITY_SCORE = Histogram(
    "cedarfix_iep3_priority_score",
    "Distribution of priority scores (0-100)",
    ["sector"],
    buckets=(0, 20, 40, 60, 80, 100),
)

# ── IEP-5 incident lifecycle (new) ────────────────────────────────────────────
IEP5_REOPEN_TOTAL = Counter(
    "cedarfix_iep5_reopen_total",
    "Incidents reopened after being marked resolved",
    ["sector"],
)
IEP5_RETRAIN_PRESSURE = Gauge(
    "cedarfix_iep5_retrain_pressure",
    "Normalised retraining-signal pressure per sector (0-1)",
    ["sector"],
)

# ── IEP-6 multimodal fusion (new) ─────────────────────────────────────────────
IEP6_FUSION_TOTAL = Counter(
    "cedarfix_iep6_image_fusion_total",
    "Image/text fusion decisions",
    ["decision"],
)
IEP6_IMAGE_CONFIDENCE = Histogram(
    "cedarfix_iep6_image_confidence",
    "Distribution of top image-hazard confidence scores",
    ["hazard"],
)

# ── IEP-8 grounded resolution co-pilot (new) ──────────────────────────────────
IEP8_PLANS_TOTAL = Counter(
    "cedarfix_iep8_plans_total",
    "Grounded resolution plans produced",
    ["outcome"],  # issued | abstained
)
IEP8_GROUNDEDNESS = Histogram(
    "cedarfix_iep8_groundedness",
    "Verified fraction of resolution-plan steps backed by retrieved evidence",
    ["sector"],
    buckets=(0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0),
)
IEP8_RETRIEVAL_SCORE = Histogram(
    "cedarfix_iep8_retrieval_score",
    "Top KB retrieval similarity score per complaint",
    ["sector"],
)
IEP8_CITATIONS = Histogram(
    "cedarfix_iep8_citations",
    "Number of evidence citations per issued plan",
    ["sector"],
    buckets=(0, 1, 2, 4, 6, 8, 12),
)
IEP8_ABSTENTIONS = Counter(
    "cedarfix_iep8_abstentions_total",
    "Plans withheld and escalated to human review by reason",
    ["reason"],  # safety_sector | no_kb_coverage | low_groundedness
)
IEP8_PLAN_CONFIDENCE = Histogram(
    "cedarfix_iep8_plan_confidence",
    "Calibrated plan confidence score (0-1) blending groundedness+retrieval+routing",
    ["sector"],
    buckets=(0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0),
)
IEP8_COVERAGE = Histogram(
    "cedarfix_iep8_coverage",
    "Fraction of complaint query-terms covered by retrieved evidence",
    ["sector"],
    buckets=(0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0),
)
IEP8_CONFLICTS = Counter(
    "cedarfix_iep8_conflicts_total",
    "Evidence conflict flags raised per sector",
    ["sector"],
)
IEP8_GAPS = Counter(
    "cedarfix_iep8_evidence_gaps_total",
    "Evidence gap diagnoses emitted (abstained complaints with missing fact-types)",
    ["sector"],
)


def add_metrics_route(app: FastAPI, service: str) -> None:
    """Attach a Prometheus ``/metrics`` exposition endpoint to a FastAPI app."""

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics() -> Response:  # noqa: D401 - simple exposition endpoint
        if not PROMETHEUS_AVAILABLE:
            return Response(
                f"# prometheus_client not installed (service={service})\n",
                media_type="text/plain",
            )
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
