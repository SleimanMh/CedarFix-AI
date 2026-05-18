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
    "IEP1LanguageSignal",
    "PairFusionGate",
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
    drift_score: int = Field(..., ge=0, le=3)
    raw_text_embedding: EmbeddingView | None = None
    normalized_text_embedding: EmbeddingView | None = None
    explanation_features: dict[str, int | float | str | bool] = Field(default_factory=dict)

    @field_validator("known_terms")
    @classmethod
    def sort_unique_known_terms(cls, value: list[str]) -> list[str]:
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
    }
