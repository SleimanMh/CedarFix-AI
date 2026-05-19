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
    HUMAN_REVIEW = "Human Review Queue"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


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
    text_analysis: Optional[TextAnalysisResult] = None
    image_analysis: Optional[ImageAnalysisResult] = None
    embedding: Optional[EmbeddingResult] = None
    clustering: Optional[ClusteringResult] = None
    priority: Optional[PriorityResult] = None
    routing: Optional[RoutingResult] = None
    explanation: Optional[ExplanationResult] = None

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

class AdminCorrection(BaseModel):
    complaint_id: str
    admin_id: str
    corrected_routing: Optional[RoutingEntity] = None
    corrected_severity: Optional[SeverityLevel] = None
    corrected_complaint_type: Optional[ComplaintType] = None
    notes: Optional[str] = None
    correction_timestamp: datetime = Field(default_factory=datetime.utcnow)
