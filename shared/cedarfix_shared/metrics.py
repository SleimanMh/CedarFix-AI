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
GATEWAY_SERVICE_CALL_DURATION = Histogram(
    "cedarfix_gateway_service_call_duration_seconds",
    "Gateway outbound service call latency",
    ["service", "endpoint", "status"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
GATEWAY_SERVICE_CALL_ERRORS = Counter(
    "cedarfix_gateway_service_call_errors_total",
    "Gateway outbound service call errors",
    ["service", "endpoint", "error_type"],
)
MULTI_COMPLAINT_SPLIT_TOTAL = Counter(
    "cedarfix_multi_complaint_split_total",
    "Complaint splitter decisions",
    ["source", "is_multi"],
)
MULTI_COMPLAINT_CHILD_COUNT = Histogram(
    "cedarfix_multi_complaint_child_count",
    "Number of child complaints produced by the splitter",
    ["source"],
    buckets=[1, 2, 3, 4, 5, 8, 10],
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
TEXT_CONFIDENCE_SCORE = Histogram(
    "cedarfix_text_confidence_score",
    "IEP-1 complaint classification confidence",
    ["category", "issue_type"],
    buckets=[0.1, 0.3, 0.5, 0.65, 0.75, 0.85, 0.95, 1.0],
)
TEXT_LOCATION_CONFIDENCE = Histogram(
    "cedarfix_text_location_confidence",
    "IEP-1 extracted location confidence",
    ["source"],
    buckets=[0.0, 0.3, 0.5, 0.65, 0.8, 0.95, 1.0],
)
TEXT_UNKNOWN_TYPE_TOTAL = Counter(
    "cedarfix_text_unknown_type_total",
    "Complaints classified with unknown issue type",
    ["category"],
)
TEXT_MISSING_LOCATION_TOTAL = Counter(
    "cedarfix_text_missing_location_total",
    "Complaints where IEP-1 could not extract or resolve a location",
    ["issue_type"],
)
TEXT_NOT_COMPLAINT_TOTAL = Counter(
    "cedarfix_text_not_complaint_total",
    "Texts classified as not being complaints",
)
TEXT_EXTRACTION_SOURCE_TOTAL = Counter(
    "cedarfix_text_extraction_source_total",
    "IEP-1 extraction path used",
    ["source"],
)
TEXT_EXTRACTION_FAILURE_TOTAL = Counter(
    "cedarfix_text_extraction_failure_total",
    "IEP-1 extractor failures by source",
    ["source", "error_type"],
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
IMAGE_INPUT_TOTAL = Counter(
    "cedarfix_image_input_total",
    "IEP-2 image input outcomes",
    ["status"],
)
IMAGE_QUALITY_FAILURE_TOTAL = Counter(
    "cedarfix_image_quality_failure_total",
    "Image quality failure reasons",
    ["issue"],
)
IMAGE_VISUAL_CONFIDENCE = Histogram(
    "cedarfix_image_visual_confidence",
    "IEP-2 visual classification confidence",
    ["category", "subcategory"],
    buckets=[0.1, 0.3, 0.5, 0.65, 0.75, 0.85, 0.95, 1.0],
)
IMAGE_DAMAGE_VISIBLE_TOTAL = Counter(
    "cedarfix_image_damage_visible_total",
    "IEP-2 damage-visible decisions",
    ["damage_visible"],
)
IMAGE_VLM_REQUEST_TOTAL = Counter(
    "cedarfix_image_vlm_request_total",
    "VLM analyzer outcomes in IEP-2",
    ["outcome"],
)

# --- Embedding Service ---
SIMILARITY_SCORE = Histogram(
    "cedarfix_similarity_score",
    "Top similarity score distribution",
    buckets=[0.5, 0.65, 0.75, 0.85, 0.92, 0.99],
)
TEXT_IMAGE_ALIGNMENT_TOTAL = Counter(
    "cedarfix_text_image_alignment_total",
    "Text-image alignment decisions from IEP-3",
    ["status", "reconciliation_status", "conflict_detected"],
)
TEXT_IMAGE_ALIGNMENT_SCORE = Histogram(
    "cedarfix_text_image_alignment_score",
    "Text-image alignment score distribution",
    ["status"],
    buckets=[0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0],
)
TEXT_IMAGE_CONFLICT_FEATURE_TOTAL = Counter(
    "cedarfix_text_image_conflict_feature_total",
    "Conflicting text-image feature counts",
    ["feature"],
)
EMBEDDING_CANDIDATE_COUNT = Histogram(
    "cedarfix_embedding_candidate_count",
    "IEP-3 candidate count after retrieval and fusion",
    ["modality"],
    buckets=[0, 1, 2, 5, 10, 20, 40],
)
RETRIEVAL_SOURCE_HITS = Counter(
    "cedarfix_retrieval_source_hits_total",
    "IEP-3 retrieved candidates by source after merge",
    ["source"],
)
QDRANT_OPERATION_DURATION = Histogram(
    "cedarfix_qdrant_operation_duration_seconds",
    "Qdrant operation latency",
    ["operation", "collection"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 3.0],
)
QDRANT_OPERATION_ERRORS = Counter(
    "cedarfix_qdrant_operation_errors_total",
    "Qdrant operation errors",
    ["operation", "collection"],
)
DUPLICATE_RATE = Counter(
    "cedarfix_duplicate_detections_total",
    "Duplicate/near-duplicate complaints detected",
    ["status"],  # DUPLICATE | NEAR_DUPLICATE | NEW
)
MATCHING_CANDIDATE_COUNT = Histogram(
    "cedarfix_matching_candidate_count",
    "IEP-4 duplicate matching candidate count",
    buckets=[0, 1, 2, 5, 10, 20, 40],
)
MATCHING_DECISION_CONFIDENCE = Histogram(
    "cedarfix_matching_decision_confidence",
    "IEP-4 duplicate decision confidence",
    ["decision"],
    buckets=[0.1, 0.3, 0.5, 0.65, 0.75, 0.85, 0.92, 0.98, 1.0],
)
MATCHING_TOP_SCORE = Histogram(
    "cedarfix_matching_top_score",
    "Top multimodal duplicate score before final decision",
    buckets=[0.1, 0.3, 0.5, 0.65, 0.75, 0.85, 0.92, 0.98, 1.0],
)
MATCHING_REVIEW_TOTAL = Counter(
    "cedarfix_matching_review_total",
    "IEP-4 duplicate decisions requiring admin review",
    ["reason"],
)
MATCHING_RECHECK_TOTAL = Counter(
    "cedarfix_matching_recheck_total",
    "IEP-4 candidates that triggered multimodal recheck logic",
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
ROUTING_SOURCE_TOTAL = Counter(
    "cedarfix_routing_source_total",
    "Routing decisions by source",
    ["source"],
)
ROUTING_REVIEW_TOTAL = Counter(
    "cedarfix_routing_review_total",
    "Routing decisions that require human review",
    ["source", "reason"],
)
RAG_RETRIEVAL_DURATION = Histogram(
    "cedarfix_rag_retrieval_duration_seconds",
    "IEP-6 routing RAG retrieval latency",
    ["status"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 3.0, 10.0],
)
RAG_CANDIDATE_COUNT = Histogram(
    "cedarfix_rag_candidate_count",
    "IEP-6 routing RAG candidate count",
    buckets=[0, 1, 2, 3, 5, 10, 20],
)
RAG_TOP_SCORE = Histogram(
    "cedarfix_rag_top_score",
    "Top routing RAG retrieval score",
    buckets=[0.1, 0.3, 0.5, 0.65, 0.75, 0.85, 0.95, 1.0],
)
RAG_NO_CANDIDATES_TOTAL = Counter(
    "cedarfix_rag_no_candidates_total",
    "Routing requests where RAG returned zero candidates",
    ["complaint_type"],
)
RAG_RETRIEVAL_ERRORS_TOTAL = Counter(
    "cedarfix_rag_retrieval_errors_total",
    "Routing RAG retrieval failures",
    ["error_type"],
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

# --- Offline GPT-4o Judge Evaluation ---
EVALUATION_COUNT = Counter(
    "cedarfix_evaluation_count_total",
    "Offline GPT-4o judge evaluations completed",
    ["prompt_version", "judge_model", "status"],
)
EVALUATION_BATCH_DURATION = Histogram(
    "cedarfix_evaluation_batch_duration_seconds",
    "Offline GPT-4o judge batch evaluation latency",
    ["prompt_version", "judge_model", "status"],
    buckets=[1.0, 3.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0],
)
EVALUATION_AVG_ROUTING_SCORE = Gauge(
    "cedarfix_evaluation_avg_routing_score",
    "Average GPT-4o judge routing score",
    ["prompt_version", "judge_model"],
)
EVALUATION_AVG_EXTRACTION_SCORE = Gauge(
    "cedarfix_evaluation_avg_extraction_score",
    "Average GPT-4o judge extraction score across text and image components",
    ["prompt_version", "judge_model"],
)
EVALUATION_AVG_OVERALL_SCORE = Gauge(
    "cedarfix_evaluation_avg_overall_score",
    "Average GPT-4o judge overall decision score",
    ["prompt_version", "judge_model"],
)
EVALUATION_TOTAL_GAUGE = Gauge(
    "cedarfix_evaluation_total",
    "Total stored offline GPT-4o judge evaluations",
    ["prompt_version", "judge_model"],
)
