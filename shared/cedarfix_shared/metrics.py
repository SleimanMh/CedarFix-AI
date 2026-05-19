"""
Prometheus metric definitions — imported by every IEP service.
Defining them here ensures consistent metric names across the platform.
"""

from prometheus_client import Counter, Histogram, Gauge, Summary

# --- Gateway ---
COMPLAINTS_TOTAL = Counter(
    "cedarfix_complaints_total",
    "Total complaints received",
    ["status"],
)
PIPELINE_DURATION = Histogram(
    "cedarfix_pipeline_duration_seconds",
    "Full pipeline duration",
    ["stage"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# --- Text Understanding ---
TEXT_ANALYSIS_DURATION = Histogram(
    "cedarfix_text_analysis_duration_seconds",
    "IEP-1 text analysis latency",
    buckets=[0.05, 0.1, 0.5, 1.0, 3.0],
)
LANGUAGE_DISTRIBUTION = Counter(
    "cedarfix_language_distribution_total",
    "Detected language counts",
    ["lang"],
)

# --- Image Understanding ---
IMAGE_ANALYSIS_DURATION = Histogram(
    "cedarfix_image_analysis_duration_seconds",
    "IEP-2 image analysis latency",
    buckets=[0.1, 0.5, 1.0, 3.0, 10.0],
)
IMAGE_RELEVANCE = Histogram(
    "cedarfix_image_relevance_score",
    "Distribution of image relevance scores",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
)

# --- Embedding Service ---
SIMILARITY_SCORE = Histogram(
    "cedarfix_similarity_score",
    "Top similarity score distribution",
    buckets=[0.5, 0.65, 0.75, 0.85, 0.92, 0.99],
)
DUPLICATE_RATE = Counter(
    "cedarfix_duplicate_detections_total",
    "Duplicate/near-duplicate complaints detected",
    ["status"],  # DUPLICATE | NEAR_DUPLICATE | NEW
)

# --- Priority Engine ---
SEVERITY_DISTRIBUTION = Counter(
    "cedarfix_severity_distribution_total",
    "Complaint severity predictions",
    ["level"],
)
PRIORITY_SCORE = Histogram(
    "cedarfix_priority_score",
    "Priority score distribution",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
)

# --- Routing Engine ---
ROUTING_CONFIDENCE = Histogram(
    "cedarfix_routing_confidence",
    "Routing confidence score distribution",
    buckets=[0.5, 0.65, 0.75, 0.85, 0.95, 1.0],
)
LOW_CONFIDENCE_ROUTING = Counter(
    "cedarfix_low_confidence_routing_total",
    "Complaints routed with confidence below threshold",
)
ROUTING_ENTITY = Counter(
    "cedarfix_routing_entity_total",
    "Complaints routed per entity",
    ["entity"],
)

# --- Monitoring / Drift ---
EMBEDDING_DRIFT_SCORE = Gauge(
    "cedarfix_embedding_drift_score",
    "Current embedding distribution drift from baseline",
)
ROUTING_ACCURACY_7D = Gauge(
    "cedarfix_routing_accuracy_7d",
    "Rolling 7-day routing accuracy (corrected / total)",
)
ADMIN_CORRECTION_RATE = Gauge(
    "cedarfix_admin_correction_rate",
    "Rate of admin corrections in the last 7 days",
)
