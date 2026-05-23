"""
CedarFix AI — Shared Pydantic Schemas
All services import from here so the contract is single-source-of-truth.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Language(str, Enum):
    ARABIC = "ar"
    FRENCH = "fr"
    ENGLISH = "en"
    ARABIZI = "arabizi"
    UNKNOWN = "unknown"


class ComplaintType(str, Enum):
    POTHOLE = "pothole"
    TRAFFIC_LIGHT = "traffic_light"
    FLOODING = "flooding"
    WASTE = "waste_accumulation"
    ELECTRICITY = "electricity_outage"
    ROAD_DAMAGE = "road_damage"
    WATER_PIPE = "water_pipe"
    SIDEWALK = "sidewalk_damage"
    STREETLIGHT = "streetlight"
    TELECOM_OUTAGE = "telecom_outage"
    OTHER = "other"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DuplicateStatus(str, Enum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    RELATED_SAME_CLUSTER = "RELATED_SAME_CLUSTER"
    NEEDS_ADMIN_REVIEW = "NEEDS_ADMIN_REVIEW"


class AlignmentStatus(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    UNRELATED = "UNRELATED"
    UNCERTAIN = "UNCERTAIN"
    NO_IMAGE = "NO_IMAGE"


class ReconciliationStatus(str, Enum):
    TEXT_AND_IMAGE_SUPPORT = "TEXT_AND_IMAGE_SUPPORT"
    IMAGE_OVERRIDES_WEAK_TEXT = "IMAGE_OVERRIDES_WEAK_TEXT"
    TEXT_OVERRIDES_WEAK_IMAGE = "TEXT_OVERRIDES_WEAK_IMAGE"
    MODAL_CONFLICT = "MODAL_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DuplicateDecisionEnum(str, Enum):
    DUPLICATE = "DUPLICATE"
    RELATED_SAME_CLUSTER = "RELATED_SAME_CLUSTER"
    NEW_INCIDENT = "NEW_INCIDENT"
    NEEDS_ADMIN_REVIEW = "NEEDS_ADMIN_REVIEW"


class ClusterActionEnum(str, Enum):
    JOIN_EXISTING_CLUSTER = "JOIN_EXISTING_CLUSTER"
    CREATE_NEW_CLUSTER = "CREATE_NEW_CLUSTER"
    FLAG_FOR_ADMIN_REVIEW = "FLAG_FOR_ADMIN_REVIEW"


class ClusterGrowthSignal(str, Enum):
    GROWING = "GROWING"
    STABLE = "STABLE"
    NEW = "NEW"
    DECLINING = "DECLINING"


class RoutingEntity(str, Enum):
    MINISTRY_PUBLIC_WORKS = "Ministry of Public Works"
    BEIRUT_MUNICIPALITY = "Beirut Municipality"
    EDL = "Electricite Du Liban"
    WATER_AUTHORITY = "Beirut Water Authority"
    INTERNAL_SECURITY = "Internal Security Forces"
    MINISTRY_ENVIRONMENT = "Ministry of Environment"
    NORTH_MUNICIPALITY = "North Lebanon Municipality"
    SOUTH_MUNICIPALITY = "South Lebanon Municipality"
    MOUNT_LEBANON_MUNICIPALITY = "Mount Lebanon Municipality"
    OGERO = "Ogero"
    HUMAN_REVIEW = "Human Review Queue"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"
    NEEDS_CLARIFICATION = "needs_clarification"   # text doesn't describe complaint but image does
    CONTRADICTION = "contradiction"               # text and image contradict each other
    INVALID_NO_COMPLAINT = "invalid_no_complaint" # neither text nor image is a complaint


class MediaValidationStatus(str, Enum):
    VALID = "valid"
    CONTRADICTION = "contradiction"
    NEEDS_CLARIFICATION = "needs_clarification"
    HUMAN_REVIEW = "human_review"
    INVALID_NO_COMPLAINT = "invalid_no_complaint"


# ---------------------------------------------------------------------------
# Request / Input Schemas
# ---------------------------------------------------------------------------

class LocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address_hint: Optional[str] = None  # e.g. "Hamra, Beirut"
    district: Optional[str] = None


class ComplaintRequest(BaseModel):
    """What the user submits to the Gateway."""
    text: str = Field(..., min_length=10, max_length=2000)
    location: Optional[LocationInput] = None
    image_filename: Optional[str] = None  # Set by gateway after upload
    user_id: Optional[str] = None         # Anonymous allowed


# ---------------------------------------------------------------------------
# IEP-1: Text Understanding Output
# ---------------------------------------------------------------------------

class TextAnalysisResult(BaseModel):
    complaint_id: str
    detected_language: Language
    normalized_text: str                  # Cleaned, optionally translated
    complaint_type: ComplaintType
    complaint_type_confidence: float = Field(..., ge=0.0, le=1.0)
    extracted_keywords: List[str] = []
    location_mentions: List[str] = []    # e.g. ["Hamra", "Cola intersection"]
    text_embedding: List[float]          # 768-dim sentence-transformer vector
    analysis_confidence: float = Field(..., ge=0.0, le=1.0)
    processing_ms: int


# ---------------------------------------------------------------------------
# IEP-2: Image Understanding Output
# ---------------------------------------------------------------------------

class ImageAnalysisResult(BaseModel):
    complaint_id: str
    image_available: bool
    detected_objects: List[str] = []      # e.g. ["pothole", "road", "water"]
    scene_description: str = ""
    visual_severity_signal: SeverityLevel = SeverityLevel.LOW
    image_embedding: List[float] = []    # 512-dim CLIP vector
    image_relevance_score: float = 0.0   # 0 = unrelated, 1 = highly relevant
    analysis_confidence: float = 0.0
    processing_ms: int = 0


# ---------------------------------------------------------------------------
# IEP-3: Embedding + Similarity Output
# ---------------------------------------------------------------------------

class SimilarComplaint(BaseModel):
    complaint_id: str
    similarity_score: float
    complaint_type: ComplaintType
    severity: SeverityLevel
    created_at: datetime


class EmbeddingResult(BaseModel):
    complaint_id: str
    fused_embedding: List[float]          # Final vector stored in Qdrant
    fusion_strategy: str                  # "weighted_avg" or "mlp"
    text_weight: float
    image_weight: float
    similar_complaints: List[SimilarComplaint] = []
    top_similarity_score: float = 0.0
    processing_ms: int


# ---------------------------------------------------------------------------
# IEP-4: Clustering + Duplicate Detection Output
# ---------------------------------------------------------------------------

class ClusteringResult(BaseModel):
    complaint_id: str
    duplicate_status: DuplicateStatus
    duplicate_of: Optional[str] = None   # complaint_id of original if DUPLICATE
    cluster_id: Optional[str] = None
    cluster_size: int = 0
    cluster_trend: str = "stable"        # "growing" | "stable" | "new"
    escalation_signal: bool = False       # True if cluster is growing fast
    processing_ms: int


# ---------------------------------------------------------------------------
# IEP-5: Priority Engine Output
# ---------------------------------------------------------------------------

class PriorityResult(BaseModel):
    complaint_id: str
    severity: SeverityLevel
    priority_score: float = Field(..., ge=0.0, le=1.0)
    urgency_factors: List[str] = []      # Human-readable factors
    cluster_size_factor: float = 0.0
    visual_severity_factor: float = 0.0
    complaint_type_factor: float = 0.0
    location_risk_factor: float = 0.0
    confidence: float = Field(..., ge=0.0, le=1.0)
    processing_ms: int


# ---------------------------------------------------------------------------
# IEP-6: Routing Engine Output
# ---------------------------------------------------------------------------

class RoutingResult(BaseModel):
    complaint_id: str
    primary_entity: RoutingEntity
    primary_confidence: float = Field(..., ge=0.0, le=1.0)
    secondary_entity: Optional[RoutingEntity] = None
    secondary_confidence: float = 0.0
    routing_rationale: List[str] = []   # Tags explaining the decision
    auto_routed: bool                    # False = flagged for human review
    requires_review: bool
    processing_ms: int


# ---------------------------------------------------------------------------
# IEP-7: Explanation Output
# ---------------------------------------------------------------------------

class ExplanationResult(BaseModel):
    complaint_id: str
    explanation_text: str                # Human-readable decision rationale
    mode: str = "template"               # "template" or "llm"
    key_factors: List[str] = []


# ---------------------------------------------------------------------------
# Final Complaint Decision (assembled by Gateway)
# ---------------------------------------------------------------------------

class ComplaintDecision(BaseModel):
    """
    The fully enriched output returned to the caller and stored in PostgreSQL.
    Every field is populated by a specific IEP.
    """
    complaint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: PipelineStatus = PipelineStatus.COMPLETED
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw input
    original_text: str
    location: Optional[LocationInput] = None
    image_filename: Optional[str] = None

    # IEP results
    text_analysis: Optional[TextUnderstandingResult] = None
    image_analysis: Optional[ImageUnderstandingResult] = None
    embedding: Optional[EmbeddingServiceResult] = None
    clustering: Optional[MultimodalClusteringResult] = None
    priority: Optional[PriorityResult] = None
    routing: Optional[RoutingResult] = None
    explanation: Optional[ExplanationResult] = None

    # Media validation gate result (populated right after IEP-1 + IEP-2)
    media_validation: Optional["MediaValidationResult"] = None

    # Summary fields (denormalized for quick query)
    complaint_type: Optional[ComplaintType] = None
    severity: Optional[SeverityLevel] = None
    priority_score: Optional[float] = None
    assigned_entity: Optional[RoutingEntity] = None
    routing_confidence: Optional[float] = None
    is_duplicate: bool = False
    total_pipeline_ms: Optional[int] = None

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Admin Correction Schema (IEP-8)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Media Validation Gate (between IEP-1/IEP-2 and IEP-3)
# ---------------------------------------------------------------------------

class MediaValidationResult(BaseModel):
    status: MediaValidationStatus
    text_is_complaint: bool
    image_has_complaint: bool
    text_detected_type: Optional[str] = None    # issue_type from text
    image_detected_type: Optional[str] = None   # visual_subcategory from image
    contradiction_reason: Optional[str] = None  # human-readable explanation
    clarification_question: Optional[str] = None


class HumanReviewItem(BaseModel):
    """Posted to review-service when a submission needs human attention."""
    complaint_id: str
    validation_status: str      # needs_clarification | human_review
    review_reason: str
    original_text: str
    image_filename: Optional[str] = None
    image_detected_type: Optional[str] = None
    text_detected_type: Optional[str] = None


class ResolveReviewItem(BaseModel):
    admin_id: str
    resolution_notes: str


# ---------------------------------------------------------------------------
# Admin Correction Schema (IEP-8)
# ---------------------------------------------------------------------------

class AdminCorrection(BaseModel):
    complaint_id: str
    admin_id: str
    corrected_routing: Optional[RoutingEntity] = None
    corrected_severity: Optional[SeverityLevel] = None
    corrected_complaint_type: Optional[ComplaintType] = None
    notes: Optional[str] = None
    correction_timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# IEP-1 v2: Structured Text Understanding (English-focused)
# ---------------------------------------------------------------------------

class LocationJSON(BaseModel):
    """Extracted and normalised location from complaint text."""
    raw: str = ""
    normalized: str = ""
    district: Optional[str] = None
    governorate: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = 0.0


class SignalsJSON(BaseModel):
    public_safety_risk: bool = False
    traffic_impact: bool = False
    corruption_signal: bool = False
    emergency_signal: bool = False


class TextUnderstandingResult(BaseModel):
    complaint_id: str
    original_text: str
    normalized_text: str
    language: str = "en"           # detected language code (ar/fr/en/arabizi)
    english_translation: Optional[str] = None  # always populated when language != en
    summary: str = ""
    category: str = ""          # roads | drainage | electricity | water | sanitation
    subcategory: str = ""       # pothole | flooding | outage …
    issue_type: ComplaintType = ComplaintType.OTHER
    location: LocationJSON = Field(default_factory=LocationJSON)
    severity: SeverityLevel = SeverityLevel.LOW
    signals: SignalsJSON = Field(default_factory=SignalsJSON)
    urgency_keywords: List[str] = []
    confidence: float = 0.0
    text_embedding_id: str = ""   # set by IEP-3 after Qdrant storage
    text_embedding: List[float] = []
    processing_ms: int = 0


# ---------------------------------------------------------------------------
# IEP-2 v2: Structured Image Understanding
# ---------------------------------------------------------------------------

class ImageQualityJSON(BaseModel):
    usable: bool = False
    quality_score: float = 0.0
    issues: List[str] = []


class VisualUnderstandingJSON(BaseModel):
    caption: str = ""
    visual_category: str = ""
    visual_subcategory: str = ""
    detected_objects: List[str] = []
    damage_visible: bool = False
    visual_severity: SeverityLevel = SeverityLevel.LOW
    confidence: float = 0.0


class ImageUnderstandingResult(BaseModel):
    complaint_id: str
    image_present: bool = False
    image_id: str = ""
    image_quality: ImageQualityJSON = Field(default_factory=ImageQualityJSON)
    visual_understanding: VisualUnderstandingJSON = Field(
        default_factory=VisualUnderstandingJSON
    )
    image_embedding_id: str = ""   # set by IEP-3 after Qdrant storage
    image_embedding: List[float] = []
    # CLIP text encoding of the complaint text (512-dim, same CLIP space as image_embedding).
    # When present, alignment.py uses direct cosine(clip_text_embedding, image_embedding)
    # as the primary intra-complaint alignment signal — no projection needed.
    # Populated by IEP-2 when complaint_text is provided in the analysis request.
    # Empty list = not computed; alignment.py falls back to the random-projection approximation.
    clip_text_embedding: List[float] = []
    processing_ms: int = 0


# ---------------------------------------------------------------------------
# IEP-3 v2: Modal Alignment + Canonical + Candidate Retrieval
# ---------------------------------------------------------------------------

class TextImageAlignment(BaseModel):
    complaint_id: str
    alignment_status: AlignmentStatus = AlignmentStatus.NO_IMAGE
    alignment_score: float = 0.0
    text_issue_type: ComplaintType = ComplaintType.OTHER
    image_issue_type: Optional[str] = None
    text_subcategory: str = ""
    image_subcategory: str = ""
    conflict_detected: bool = False
    conflict_reason: Optional[str] = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.INSUFFICIENT_EVIDENCE
    reconciliation_note: str = ""


class CanonicalLocationJSON(BaseModel):
    normalized_location: str = ""
    district: Optional[str] = None
    governorate: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class CanonicalComplaint(BaseModel):
    complaint_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""
    category: str = ""
    subcategory: str = ""
    issue_type: ComplaintType = ComplaintType.OTHER
    severity: SeverityLevel = SeverityLevel.LOW
    location: CanonicalLocationJSON = Field(default_factory=CanonicalLocationJSON)
    signals: SignalsJSON = Field(default_factory=SignalsJSON)
    modality: str = "TEXT_ONLY"   # TEXT_ONLY | TEXT_AND_IMAGE
    text_embedding_id: str = ""
    image_embedding_id: str = ""


class RawCandidate(BaseModel):
    """Pre-scoring candidate from independent retrieval (before IEP-4 scoring)."""
    complaint_id: str
    cluster_id: Optional[str] = None
    summary: str = ""
    issue_type: ComplaintType = ComplaintType.OTHER
    subcategory: str = ""
    location: CanonicalLocationJSON = Field(default_factory=CanonicalLocationJSON)
    timestamp: Optional[datetime] = None
    severity: SeverityLevel = SeverityLevel.LOW
    text_embedding: List[float] = []
    image_embedding: List[float] = []
    sources: List[str] = []             # ["text_search", "image_search", …]
    raw_text_similarity: float = 0.0
    raw_image_similarity: float = 0.0


class EmbeddingServiceResult(BaseModel):
    """Full IEP-3 output consumed by IEP-4."""
    complaint_id: str
    canonical: CanonicalComplaint
    alignment: TextImageAlignment
    candidates: List[RawCandidate] = []
    text_embedding: List[float] = []
    image_embedding: List[float] = []
    processing_ms: int = 0


# ---------------------------------------------------------------------------
# IEP-4 v2: Multimodal Scoring, Reconciliation, Decision, Cluster Assignment
# ---------------------------------------------------------------------------

class SimilarityScores(BaseModel):
    text_similarity: float = 0.0
    image_similarity: float = 0.0
    location_similarity: float = 0.5
    time_similarity: float = 0.5
    issue_type_similarity: float = 0.0


class DuplicateCandidate(BaseModel):
    candidate_complaint_id: str
    candidate_cluster_id: Optional[str] = None
    candidate_summary: str = ""
    candidate_issue_type: ComplaintType = ComplaintType.OTHER
    candidate_subcategory: str = ""
    candidate_location: CanonicalLocationJSON = Field(default_factory=CanonicalLocationJSON)
    similarity_scores: SimilarityScores = Field(default_factory=SimilarityScores)
    candidate_source: List[str] = []
    multimodal_score: float = 0.0
    recheck_triggered: bool = False
    recheck_reason: Optional[str] = None
    per_candidate_reconciliation: ReconciliationStatus = ReconciliationStatus.INSUFFICIENT_EVIDENCE


class EvidenceJSON(BaseModel):
    strongest_signal: str = ""
    text_similarity: float = 0.0
    image_similarity: float = 0.0
    location_similarity: float = 0.0
    time_similarity: float = 0.0
    issue_type_similarity: float = 0.0
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.INSUFFICIENT_EVIDENCE


class DuplicateDecision(BaseModel):
    complaint_id: str
    duplicate_decision: DuplicateDecisionEnum = DuplicateDecisionEnum.NEW_INCIDENT
    decision_confidence: float = 0.0
    matched_complaint_id: Optional[str] = None
    matched_cluster_id: Optional[str] = None
    decision_reason: str = ""
    evidence: EvidenceJSON = Field(default_factory=EvidenceJSON)
    requires_admin_review: bool = False
    review_reasons: List[str] = []


class ClusterAssignment(BaseModel):
    complaint_id: str
    cluster_action: ClusterActionEnum = ClusterActionEnum.CREATE_NEW_CLUSTER
    cluster_id: Optional[str] = None
    cluster_type: Optional[str] = None
    cluster_subcategory: Optional[str] = None
    cluster_location: Optional[str] = None
    cluster_size_before: int = 0
    cluster_size_after: int = 0
    cluster_growth_signal: ClusterGrowthSignal = ClusterGrowthSignal.NEW
    priority_escalation_signal: bool = False
    cluster_note: str = ""
    linked_to_complaint_id: Optional[str] = None  # set when DUPLICATE — link kept, count still incremented


class AdminReviewJSON(BaseModel):
    required: bool = False
    reasons: List[str] = []


class MultimodalClusteringResult(BaseModel):
    """
    IEP-4 output.  Extends the old ClusteringResult fields so IEP-5/6 still work,
    while exposing the full multimodal reasoning detail.
    """
    # ── Backwards-compatible fields (IEP-5/6 read these) ──────────────────
    complaint_id: str
    duplicate_status: DuplicateStatus = DuplicateStatus.NEW
    duplicate_of: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_size: int = 0
    cluster_trend: str = "stable"
    escalation_signal: bool = False
    processing_ms: int = 0

    # ── New multimodal fields ──────────────────────────────────────────────
    duplicate_decision: DuplicateDecisionEnum = DuplicateDecisionEnum.NEW_INCIDENT
    decision_confidence: float = 0.0
    matched_complaint_id: Optional[str] = None
    matched_cluster_id: Optional[str] = None
    decision_reason: str = ""
    evidence: EvidenceJSON = Field(default_factory=EvidenceJSON)
    cluster_assignment: Optional[ClusterAssignment] = None
    modal_alignment: Optional[TextImageAlignment] = None
    top_candidates: List[DuplicateCandidate] = []
    requires_admin_review: bool = False
    review_reasons: List[str] = []
    canonical: Optional[CanonicalComplaint] = None


class RoutingPayload(BaseModel):
    """Assembled by IEP-4; forwarded to IEP-5 via gateway."""
    complaint_id: str
    canonical_complaint: CanonicalComplaint
    modal_alignment: TextImageAlignment
    duplicate_result: DuplicateDecision
    cluster_result: ClusterAssignment
    admin_review: AdminReviewJSON = Field(default_factory=AdminReviewJSON)
    next_stage: str = "ROUTING_ENGINE"
    processing_ms: int = 0
