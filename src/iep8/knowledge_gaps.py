"""IEP-8 closed-loop active knowledge acquisition.

The co-pilot's *failures* are its most valuable output. Every time IEP-8
abstains for lack of coverage it emits a structured :class:`EvidenceGap`. This
module aggregates those gaps across complaints into a **ranked data-acquisition
backlog** — a prioritised, evidence-based answer to "which authority's facts
should we source next, and why?".

The ranking is pure citizen-impact: a gap that blocks 40 complaints outranks
one that blocks 2, with life-safety gaps surfaced first. This turns retrieval
misses into a self-maintaining roadmap for growing the knowledge-base moat.

Everything here is pure and deterministic — it operates on already-produced
plans (or their persisted JSON), so it is trivially unit-testable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from src.shared.resolution_schemas import EvidenceGap, GroundedResolutionPlan

# Severity → ranking weight (life-safety gaps float to the top).
_SEVERITY_WEIGHT = {"high": 3.0, "medium": 1.0, "low": 0.5}


class AcquisitionItem(dict):
    """A single ranked backlog entry (a plain dict for clean JSON output)."""


def _gaps_from_plan(plan: GroundedResolutionPlan | dict[str, Any]) -> list[EvidenceGap]:
    if isinstance(plan, GroundedResolutionPlan):
        return list(plan.evidence_gaps)
    raw = plan.get("evidence_gaps") or []
    out: list[EvidenceGap] = []
    for item in raw:
        try:
            out.append(EvidenceGap.model_validate(item))
        except Exception:  # noqa: BLE001 - skip malformed persisted rows
            continue
    return out


def iter_gaps(plans: Iterable[GroundedResolutionPlan | dict[str, Any]]) -> list[EvidenceGap]:
    """Flatten the evidence gaps from a stream of plans (objects or JSON)."""
    gaps: list[EvidenceGap] = []
    for plan in plans:
        gaps.extend(_gaps_from_plan(plan))
    return gaps


def rank_acquisition_backlog(gaps: Iterable[EvidenceGap]) -> list[AcquisitionItem]:
    """Aggregate gaps into a ranked acquisition backlog.

    Grouped by (sector, entity). Each item reports how many complaints it
    blocks, the most-requested missing fact types, the most common uncovered
    query terms, and a priority score = blocked_count × severity_weight.
    """
    blocked: Counter[tuple[str, str]] = Counter()
    severity: dict[tuple[str, str], float] = defaultdict(float)
    fact_types: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    terms: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    reasons: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)

    for gap in gaps:
        key = (gap.sector or "UNKNOWN", gap.entity or "UNKNOWN")
        blocked[key] += 1
        severity[key] = max(severity[key], _SEVERITY_WEIGHT.get(gap.severity, 1.0))
        for ft in gap.missing_fact_types:
            fact_types[key][ft] += 1
        for term in gap.query_terms:
            terms[key][term] += 1
        if gap.reason:
            reasons[key][gap.reason] += 1

    backlog: list[AcquisitionItem] = []
    for key, count in blocked.items():
        sector, entity = key
        weight = severity[key]
        backlog.append(
            AcquisitionItem(
                sector=sector,
                entity=entity,
                blocked_complaints=count,
                priority_score=round(count * weight, 3),
                severity_weight=weight,
                missing_fact_types=[ft for ft, _ in fact_types[key].most_common(5)],
                top_query_terms=[t for t, _ in terms[key].most_common(8)],
                reasons=dict(reasons[key].most_common()),
            )
        )

    backlog.sort(
        key=lambda item: (item["priority_score"], item["blocked_complaints"], item["entity"]),
        reverse=True,
    )
    return backlog


def acquisition_backlog_from_plans(
    plans: Iterable[GroundedResolutionPlan | dict[str, Any]],
) -> list[AcquisitionItem]:
    """Convenience: plans (objects or persisted JSON) → ranked backlog."""
    return rank_acquisition_backlog(iter_gaps(plans))
