"""IEP-8 grounded-resolution contracts and pure faithfulness math.

IEP-8 is the **Grounded Agentic Resolution Co-Pilot**: given a routed
complaint it retrieves the relevant verified facts from the CedarFix entity
knowledge base, synthesises a citizen + operations resolution plan, and then
*verifies* that every claim in that plan is supported by retrieved evidence.
Unsupported claims are dropped; if the plan cannot be sufficiently grounded —
or the sector is safety-critical, or retrieval confidence is low — IEP-8
**abstains** and forces human review instead of advising.

This module holds the data contracts and the dependency-free faithfulness
math (tokenisation, lexical support scoring, groundedness) so the trust layer
can be unit-tested without any model weights, network, or LLM.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EvidenceChunk",
    "ResolutionStep",
    "EvidenceGap",
    "ConflictFlag",
    "GroundedResolutionPlan",
    "tokenize",
    "support_score",
    "is_supported",
    "groundedness",
    "coverage_score",
    "plan_confidence_score",
    "SUPPORT_THRESHOLD",
    "MIN_GROUNDEDNESS",
    "MIN_RETRIEVAL_SCORE",
    "ABSTAIN_SECTORS",
    "CONFLICT_FACT_TYPES",
    "SECTOR_EXPECTED_FACT_TYPES",
]

# ── Trust thresholds ──────────────────────────────────────────────────────────
# A single step counts as "supported" when its lexical overlap with at least one
# cited evidence chunk reaches SUPPORT_THRESHOLD.
SUPPORT_THRESHOLD: float = 0.30
# A plan is auto-issuable only when this fraction of its steps are supported.
MIN_GROUNDEDNESS: float = 0.80
# Below this top retrieval score, the KB does not actually cover the complaint.
MIN_RETRIEVAL_SCORE: float = 0.05
# Sectors where we never auto-advise — life-safety stays with humans.
ABSTAIN_SECTORS: frozenset[str] = frozenset({"SAFETY", "ELECTRICITY", "FLOODING"})
# Fact types whose retrieved values must be internally consistent before we act:
# a contradiction here (two different hotlines, two different SLAs) is unsafe to
# auto-advise on, so IEP-8 flags it and defers to a human.
CONFLICT_FACT_TYPES: frozenset[str] = frozenset(
    {"operational_contact", "deadline_or_sla", "emergency_instruction"}
)
# What a citizen actually needs answered per sector. When the KB cannot cover a
# complaint, these are the fact types whose *absence* becomes a ranked data-
# acquisition task (the closed-loop active-learning signal).
SECTOR_EXPECTED_FACT_TYPES: dict[str, tuple[str, ...]] = {
    "ELECTRICITY": ("operational_contact", "complaint_process", "deadline_or_sla"),
    "WATER": ("operational_contact", "service_area", "complaint_process"),
    "ROADS": ("legal_responsibility", "complaint_process", "operational_contact"),
    "WASTE": ("legal_responsibility", "complaint_process", "operational_contact"),
    "FLOODING": ("emergency_instruction", "operational_contact", "legal_responsibility"),
    "SAFETY": ("emergency_instruction", "operational_contact"),
    "TELECOM": ("operational_contact", "complaint_process", "service_area"),
}
_DEFAULT_EXPECTED_FACT_TYPES: tuple[str, ...] = (
    "legal_responsibility",
    "operational_contact",
    "complaint_process",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Common words that should not count toward grounding overlap.
_STOPWORDS: frozenset[str] = frozenset(
    """
    the a an and or of to for in on at by with from is are be was were this that
    these those it its as your you we our their they them he she his her not no
    if then than into over under out up down off via per which who whom whose
    will would can could should may might must do does did done has have had
    """.split()
)


def tokenize(text: str | None) -> set[str]:
    """Lower-case content-word token set (stopwords removed)."""
    if not text:
        return set()
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


class EvidenceChunk(BaseModel):
    """A single retrieved, citable fact from the entity knowledge base."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(..., min_length=1)
    fact_id: str = Field(..., min_length=1)
    fact_type: str = Field(default="", max_length=64)
    text: str = Field(..., min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    confidence: str = Field(default="medium")  # high | medium | low
    human_review_required: bool = False
    score: float = Field(default=0.0, ge=0.0)  # retrieval similarity

    @property
    def citation(self) -> str:
        srcs = ";".join(self.source_ids[:3]) if self.source_ids else "no_source"
        return f"[{self.fact_id} · {srcs}]"


class ResolutionStep(BaseModel):
    """One grounded instruction line with its supporting citations."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., min_length=1)  # action | contact | boundary | safety
    text: str = Field(..., min_length=1)
    cited_fact_ids: list[str] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)
    support: float = Field(default=0.0, ge=0.0, le=1.0)
    supported: bool = False


class EvidenceGap(BaseModel):
    """A diagnosed hole in the knowledge base, emitted when IEP-8 abstains.

    Aggregated across complaints these become a *ranked data-acquisition
    backlog*: the system's own retrieval failures tell operators exactly which
    authority's facts to source next, ranked by how many citizens they block.
    """

    model_config = ConfigDict(extra="forbid")

    sector: str = Field(default="", max_length=32)
    entity: str | None = None
    missing_fact_types: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=64)
    severity: str = Field(default="medium")  # high | medium


class ConflictFlag(BaseModel):
    """Two retrieved facts of the same kind that contradict each other."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(..., min_length=1)
    fact_type: str = Field(default="", max_length=64)
    fact_ids: list[str] = Field(default_factory=list)
    detail: str = Field(default="", max_length=200)


class GroundedResolutionPlan(BaseModel):
    """The verified output packet stored on the complaint."""

    model_config = ConfigDict(extra="forbid")

    complaint_id: str = Field(..., min_length=1)
    routing_sector: str | None = None
    routing_entity: str | None = None
    abstained: bool = False
    abstain_reason: str = Field(default="", max_length=160)
    force_hitl: bool = False
    groundedness: float = Field(default=0.0, ge=0.0, le=1.0)
    top_retrieval_score: float = Field(default=0.0, ge=0.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    plan_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    steps: list[ResolutionStep] = Field(default_factory=list)
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    conflicts: list[ConflictFlag] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    citizen_summary: str = Field(default="", max_length=2000)
    ops_brief: str = Field(default="", max_length=2400)
    generator: str = Field(default="extractive")  # extractive | llm_constrained
    model_name: str = "cedarfix-grounded-rag-v1"


def support_score(claim: str, evidence_text: str) -> float:
    """Fraction of the claim's content tokens that appear in the evidence.

    This is a deliberately conservative, dependency-free entailment proxy: a
    claim is only "supported" when most of what it asserts is lexically present
    in a retrieved fact. It is the verifier that lets IEP-8 *catch* a
    hallucinated claim (one whose tokens are not in any retrieved evidence).
    """
    claim_tokens = tokenize(claim)
    if not claim_tokens:
        return 0.0
    evidence_tokens = tokenize(evidence_text)
    if not evidence_tokens:
        return 0.0
    overlap = claim_tokens & evidence_tokens
    return len(overlap) / len(claim_tokens)


def is_supported(claim: str, evidence_texts: list[str], threshold: float = SUPPORT_THRESHOLD) -> bool:
    """True when the claim is supported by at least one evidence chunk."""
    return any(support_score(claim, ev) >= threshold for ev in evidence_texts)


def groundedness(steps: list[ResolutionStep]) -> float:
    """Fraction of steps that are evidence-supported (the plan's trust score)."""
    if not steps:
        return 0.0
    return sum(1 for s in steps if s.supported) / len(steps)


def coverage_score(complaint_text: str, evidence_texts: list[str]) -> float:
    """Fraction of the complaint's content terms present in retrieved evidence.

    Distinct from groundedness (which scores the *output* steps): coverage
    scores the *input* — how much of what the citizen actually said the KB can
    even speak to. Low coverage is the precise signal of a knowledge gap.
    """
    terms = tokenize(complaint_text)
    if not terms:
        return 0.0
    evidence_terms: set[str] = set()
    for ev in evidence_texts:
        evidence_terms |= tokenize(ev)
    return len(terms & evidence_terms) / len(terms)


def plan_confidence_score(
    plan_groundedness: float,
    top_retrieval_score: float,
    routing_confidence: float | None = None,
) -> float:
    """Calibrated 0–1 confidence blending faithfulness, retrieval and routing.

    Deliberately conservative: groundedness dominates (a plan we cannot verify
    is never confident no matter how sure the router was). Retrieval similarity
    is normalised against a strong-match reference of 0.25 cosine.
    """
    retrieval_signal = min(max(top_retrieval_score, 0.0) / 0.25, 1.0)
    routing = 0.7 if routing_confidence is None else max(0.0, min(routing_confidence, 1.0))
    score = 0.55 * plan_groundedness + 0.30 * retrieval_signal + 0.15 * routing
    return round(max(0.0, min(score, 1.0)), 4)
