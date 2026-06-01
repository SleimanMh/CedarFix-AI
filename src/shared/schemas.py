from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Below this route-confidence level, force_hitl() treats routing as too uncertain
# and requires HITL review regardless of drift score.
ROUTE_CONFIDENCE_THRESHOLD: float = 0.65

__all__ = [
    "ROUTE_CONFIDENCE_THRESHOLD",
    "Language",
    "ScriptProfile",
    "OOVRiskHint",
    "EmbeddingView",
    "OOVToken",
    "IssueEvidenceTerm",
    "IssueCandidate",
    "IEP1LanguageSignal",
    "PairFusionGate",
    "DuplicateMatchEvidence",
    "IncidentIntelligence",
    "RoutingDecisionEvidence",
    "schema_json_examples",
]


class Language(str, Enum):
    ARABIC = "ar"
    ARABIZI = "arabizi"
    ENGLISH = "en"
    FRENCH = "fr"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ScriptProfile(str, Enum):
    ARABIC_SCRIPT = "arabic_script"
    LATIN_ARABIZI = "latin_arabizi"
    LATIN_OTHER = "latin_other"
    MIXED_LATIN = "mixed_latin"
    MIXED_SCRIPT = "mixed_script"
    UNKNOWN = "unknown"


class OOVRiskHint(str, Enum):
    SAFETY_LEXICAL_HINT = "SAFETY_LEXICAL_HINT"
    HIGH_IMPACT_CONTEXT = "HIGH_IMPACT_CONTEXT"
    HITL_CONTEXT = "HITL_CONTEXT"
    LANGUAGE_DRIFT = "LANGUAGE_DRIFT"


class EmbeddingView(BaseModel):
    """Embedding lineage without forcing APIs to move huge vectors in every call."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(..., min_length=1)
    dimension: int = Field(..., ge=1)
    vector: list[float] | None = None
    artifact_uri: str | None = None

    @model_validator(mode="after")
    def validate_vector_shape(self) -> "EmbeddingView":
        if self.vector is not None and len(self.vector) != self.dimension:
            raise ValueError("vector length must equal dimension")
        if self.vector is None and not self.artifact_uri:
            raise ValueError("embedding must provide vector or artifact_uri")
        return self


class OOVToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., min_length=1)
    raw_variants: list[str] = Field(default_factory=list)
    risk_hint: OOVRiskHint = OOVRiskHint.LANGUAGE_DRIFT
    suggested_action: str = Field(default="NEEDS_MORE_EXAMPLES", min_length=1)
    matched_context: str = Field(default="", description="Short phrase explaining why this token matters.")


class IssueEvidenceTerm(BaseModel):
    """One vocabulary-backed term that contributed to issue classification."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(..., min_length=1)
    sector: str = Field(..., min_length=1)
    issue_type: str = Field(..., min_length=1)
    source: str = Field(default="vocab_token_issue_map", min_length=1)
    contribution: float = Field(default=1.0, ge=0.0)


class IssueCandidate(BaseModel):
    """Ranked issue hypothesis emitted by IEP-1 for review and explanation."""

    model_config = ConfigDict(extra="forbid")

    sector: str = Field(..., min_length=1)
    issue_type: str = Field(..., min_length=1)
    evidence_count: int = Field(..., ge=0)
    matched_terms: list[str] = Field(default_factory=list)
    sector_keyword_hits: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    selected: bool = False
    reason: str = Field(..., min_length=1)

    @field_validator("matched_terms", "sector_keyword_hits")
    @classmethod
    def sort_unique_terms(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class IEP1LanguageSignal(BaseModel):
    """Output contract for IEP-1 multilingual signal extraction.

    This is a contract, not a claim that the v1 heuristic probe is the final
    model. The trained IEP-1 service must preserve these fields so EEP,
    HITL, MLflow, and Grafana can reason about language drift consistently.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str | None = None
    language: Language
    script_profile: ScriptProfile
    raw_text: str = Field(..., min_length=1)
    normalized_text: str = Field(..., min_length=1)
    normalization_applied: bool
    normalization_confidence: float = Field(..., ge=0.0, le=1.0)
    normalization_coverage: float = Field(..., ge=0.0, le=1.0)
    arabizi_marker_count: int = Field(..., ge=0)
    arabizi_marker_density: float = Field(..., ge=0.0, le=1.0)
    code_mix_ratio: float = Field(..., ge=0.0, le=1.0)
    oov_token_count: int = Field(..., ge=0)
    oov_high_risk_count: int = Field(..., ge=0)
    oov_tokens: list[OOVToken] = Field(default_factory=list)
    known_terms: list[str] = Field(default_factory=list)
    issue_evidence_terms: list[IssueEvidenceTerm] = Field(default_factory=list)
    issue_candidates: list[IssueCandidate] = Field(default_factory=list)
    model_issue_candidates: list[IssueCandidate] = Field(default_factory=list)
    language_risk_reasons: list[str] = Field(default_factory=list)
    review_recommendation: str = Field(default="AUTO_ROUTE_ELIGIBLE", min_length=1)
    drift_score: int = Field(..., ge=0, le=3)
    raw_text_embedding: EmbeddingView | None = None
    normalized_text_embedding: EmbeddingView | None = None
    explanation_features: dict[str, int | float | str | bool] = Field(default_factory=dict)
    classification_trace: dict[str, Any] = Field(default_factory=dict)

    @field_validator("known_terms")
    @classmethod
    def sort_unique_known_terms(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @field_validator("language_risk_reasons")
    @classmethod
    def sort_unique_risk_reasons(cls, value: list[str]) -> list[str]:
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_counts_and_reliability(self) -> "IEP1LanguageSignal":
        if self.oov_token_count != len(self.oov_tokens):
            raise ValueError("oov_token_count must equal len(oov_tokens)")
        high_risk = sum(1 for item in self.oov_tokens if item.risk_hint != OOVRiskHint.LANGUAGE_DRIFT)
        if self.oov_high_risk_count != high_risk:
            raise ValueError("oov_high_risk_count must match non-language-drift OOV tokens")
        if self.oov_high_risk_count and self.drift_score < 2:
            raise ValueError("high-risk OOV tokens require drift_score >= 2")
        if self.normalization_applied and self.language not in {Language.ARABIZI, Language.MIXED}:
            raise ValueError("normalization_applied should only be true for arabizi or mixed inputs")
        return self

    def force_hitl(self, route_confidence: float | None = None, route_threshold: float = ROUTE_CONFIDENCE_THRESHOLD) -> bool:
        """Conservative EEP/HITL rule for language-risk gating."""

        if self.drift_score >= 2 or self.oov_high_risk_count > 0:
            return True
        if self.explanation_features.get("semantic_ambiguity"):
            return True
        if route_confidence is not None and route_confidence < route_threshold:
            return True
        return False


class PairFusionGate(BaseModel):
    """Small contract used by IEP-2 tests for duplicate boundary behavior."""

    model_config = ConfigDict(extra="forbid")

    report_id_a: str
    report_id_b: str
    distance_m: float = Field(..., ge=0.0)
    semantic_duplicate_candidate: bool
    auto_merge_radius_m: float = Field(default=200.0, gt=0.0)
    expected_pair_label: str

    @property
    def allow_auto_merge_by_geo(self) -> bool:
        return self.semantic_duplicate_candidate and self.distance_m <= self.auto_merge_radius_m


class DuplicateMatchEvidence(BaseModel):
    """Inspectable IEP-2 duplicate decision evidence for one complaint."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    incident_id: str = Field(..., min_length=1)
    is_duplicate: bool
    match_complaint_id: str | None = None
    similarity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    geo_distance_m: float | None = Field(default=None, ge=0.0)
    decision_reason: str = Field(..., min_length=1)
    candidate_count: int = Field(..., ge=0)
    candidates_within_radius: int = Field(..., ge=0)
    embedding_comparison_count: int = Field(..., ge=0)
    semantic_threshold: float = Field(..., ge=0.0, le=1.0)
    geo_radius_m: float = Field(..., gt=0.0)
    fusion_score: float | None = Field(default=None, ge=0.0, le=1.0)
    fusion_label: str | None = None
    fusion_features: dict[str, int | float | str | bool | None] = Field(default_factory=dict)


class IncidentIntelligence(BaseModel):
    """Durable incident/cluster packet emitted by IEP-2."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    incident_id: str = Field(..., min_length=1)
    is_duplicate: bool
    matched_complaint_id: str | None = None
    incident_lifecycle_state: str = Field(..., min_length=1)
    review_recommendation: str = Field(..., min_length=1)
    cluster_size: int = Field(..., ge=1)
    cluster_duplicate_count: int = Field(..., ge=0)
    cluster_report_ids: list[str] = Field(default_factory=list)
    cluster_issue_types: list[str] = Field(default_factory=list)
    match_evidence: DuplicateMatchEvidence

    @field_validator("cluster_report_ids", "cluster_issue_types")
    @classmethod
    def sort_unique_cluster_values(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


class RoutingDecisionEvidence(BaseModel):
    """Durable IEP-3 routing packet for admin review and audit."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    router_version: str = Field(..., min_length=1)
    routing_sector: str = Field(..., min_length=1)
    routing_entity: str = Field(..., min_length=1)
    routing_confidence: float = Field(..., ge=0.0, le=1.0)
    priority_score: float = Field(..., ge=0.0, le=100.0)
    hitl_required: bool
    hitl_reason: str | None = None
    hitl_reason_codes: list[str] = Field(default_factory=list)
    auto_route_eligible: bool
    issue_type: str | None = None
    issue_type_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    kb_route_reason: str | None = None
    kb_complaint_type_id: str | None = None
    kb_complaint_type: str | None = None
    kb_primary_entity_raw: str | None = None
    kb_secondary_entity: str | None = None
    kb_location_method: str | None = None
    kb_municipality_id: str | None = None
    kb_municipality_name: str | None = None
    kb_boundary_entity: str | None = None
    kb_warnings: list[str] = Field(default_factory=list)
    shap_top3: dict[str, Any] = Field(default_factory=dict)
    routing_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    routing_risk_factors: list[str] = Field(default_factory=list)
    neuro_symbolic_trace: dict[str, int | float | str | bool | list[str] | None] = Field(default_factory=dict)

    @field_validator("hitl_reason_codes", "kb_warnings", "routing_risk_factors")
    @classmethod
    def sort_unique_route_values(cls, value: list[str]) -> list[str]:
        return sorted(set(value))


def schema_json_examples() -> dict[str, Any]:
    return {
        "language_signal": IEP1LanguageSignal(
            language=Language.ARABIZI,
            script_profile=ScriptProfile.LATIN_ARABIZI,
            raw_text="fi jora kbire 3al tari2 w l wad3 m5atra ktir",
            normalized_text="في حفرة كبيرة على الطريق والوضع خطير كثير",
            normalization_applied=True,
            normalization_confidence=0.71,
            normalization_coverage=0.71,
            arabizi_marker_count=2,
            arabizi_marker_density=0.25,
            code_mix_ratio=0.0,
            oov_token_count=1,
            oov_high_risk_count=1,
            oov_tokens=[
                OOVToken(
                    token="m5atra",
                    raw_variants=["m5atra"],
                    risk_hint=OOVRiskHint.SAFETY_LEXICAL_HINT,
                    suggested_action="NEEDS_MORE_EXAMPLES",
                    matched_context="Unknown risk modifier near known pothole term.",
                )
            ],
            known_terms=["jora", "tari2"],
            drift_score=2,
            explanation_features={"semantic_ambiguity": False, "vocab_version": "1.4.0"},
        ).model_dump(),
        "incident_intelligence": IncidentIntelligence(
            complaint_id="C-002",
            incident_id="INC-001",
            is_duplicate=True,
            matched_complaint_id="C-001",
            incident_lifecycle_state="EMERGING",
            review_recommendation="AUTO_ATTACH_TO_INCIDENT",
            cluster_size=2,
            cluster_duplicate_count=1,
            cluster_report_ids=["C-001", "C-002"],
            cluster_issue_types=["road_pothole"],
            match_evidence=DuplicateMatchEvidence(
                complaint_id="C-002",
                incident_id="INC-001",
                is_duplicate=True,
                match_complaint_id="C-001",
                similarity_score=0.93,
                geo_distance_m=42.0,
                decision_reason="semantic_dup sim=0.930 dist=42m",
                candidate_count=1,
                candidates_within_radius=1,
                embedding_comparison_count=1,
                semantic_threshold=0.88,
                geo_radius_m=500.0,
            ),
        ).model_dump(),
        "routing_decision_evidence": RoutingDecisionEvidence(
            complaint_id="C-002",
            router_version="route_complaint_kb",
            routing_sector="ROADS",
            routing_entity="MUN",
            routing_confidence=0.78,
            priority_score=65.0,
            hitl_required=False,
            hitl_reason=None,
            hitl_reason_codes=[],
            auto_route_eligible=True,
            issue_type="road_pothole",
            issue_type_confidence=0.84,
            kb_route_reason="sector=ROADS | type=local_road_pothole | rule=RR-007",
            kb_complaint_type_id="CT-ROAD-001",
            kb_complaint_type="local_road_pothole",
            kb_primary_entity_raw="MUN-54111",
            kb_secondary_entity="",
            kb_location_method="gps",
            kb_municipality_id="54111",
            kb_municipality_name="Beirut",
            kb_warnings=[],
            shap_top3={"router_version": "route_complaint_kb"},
        ).model_dump(),
    }
