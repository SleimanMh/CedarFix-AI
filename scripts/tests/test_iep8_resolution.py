"""IEP-8 grounded resolution co-pilot — unit tests.

Covers the three guarantees that make IEP-8 trustworthy:
1. **Relevance** — retrieval surfaces the right entity's facts for a complaint.
2. **Faithfulness** — every citation in a plan points at a *real* retrieved
   fact/source; the verifier drops fabricated (hallucinated) claims.
3. **Safety** — life-safety sectors and low-coverage complaints abstain to HITL.

All deterministic; no model weights or network required.
"""
from __future__ import annotations

import unittest

from src.iep8.planner import build_plan, verify_steps
from src.iep8.retriever import EntityKnowledgeBase, get_kb
from src.shared.resolution_schemas import (
    ABSTAIN_SECTORS,
    MIN_GROUNDEDNESS,
    EvidenceChunk,
    ResolutionStep,
    support_score,
)


class TestRetriever(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kb = get_kb()

    def test_kb_loads_facts(self) -> None:
        self.assertGreater(self.kb.size, 20)

    def test_waste_complaint_surfaces_municipality(self) -> None:
        chunks = self.kb.retrieve(
            "garbage piling up uncollected on our street for days",
            sector="WASTE",
            entity="MUN",
            k=6,
        )
        self.assertTrue(chunks)
        entities = {c.entity_id for c in chunks}
        self.assertIn("MUN", entities)

    def test_retrieval_is_deterministic(self) -> None:
        q = "broken water pipe flooding the road"
        a = self.kb.retrieve(q, sector="WATER", entity=None, k=5)
        b = self.kb.retrieve(q, sector="WATER", entity=None, k=5)
        self.assertEqual([c.fact_id for c in a], [c.fact_id for c in b])

    def test_scores_are_sorted_descending(self) -> None:
        chunks = self.kb.retrieve("street lighting outage at night", sector="ROADS", k=6)
        scores = [c.score for c in chunks]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestSupportMath(unittest.TestCase):
    def test_support_score_rewards_overlap(self) -> None:
        ev = "Municipalities handle solid waste collection and street cleaning."
        self.assertGreater(support_score("handle solid waste collection", ev), 0.5)

    def test_support_score_rejects_fabrication(self) -> None:
        ev = "Municipalities handle solid waste collection and street cleaning."
        # A fabricated phone number / unrelated claim has ~no token overlap.
        self.assertLess(support_score("call the national hotline 1-800-555-0000", ev), 0.3)


class TestVerifier(unittest.TestCase):
    def test_verifier_flags_hallucinated_step(self) -> None:
        evidence = {
            "MUN-F001": EvidenceChunk(
                entity_id="MUN",
                fact_id="MUN-F001",
                fact_type="legal_responsibility",
                text="Municipalities handle solid waste collection and street cleaning.",
                source_ids=["SRC-MUN-LAW"],
            )
        }
        grounded = ResolutionStep(
            kind="action",
            text="Municipalities handle solid waste collection",
            cited_fact_ids=["MUN-F001"],
            cited_source_ids=["SRC-MUN-LAW"],
        )
        hallucinated = ResolutionStep(
            kind="contact",
            text="Dial the secret emergency drone dispatch at 1-900-FAKE-NUM",
            cited_fact_ids=["MUN-F001"],
            cited_source_ids=["SRC-MUN-LAW"],
        )
        verified = verify_steps([grounded, hallucinated], evidence)
        by_kind = {s.kind: s for s in verified}
        self.assertTrue(by_kind["action"].supported)
        self.assertFalse(by_kind["contact"].supported)


class TestPlanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kb = get_kb()

    def test_issued_plan_has_only_real_citations(self) -> None:
        plan = build_plan(
            complaint_id="C-WASTE",
            routing_sector="WASTE",
            routing_entity="MUN",
            complaint_text="garbage uncollected for a week on our street",
            routing_confidence=0.8,
            hitl_required=False,
            kb=self.kb,
        )
        real_fact_ids = {c.fact_id for c in plan.evidence}
        real_source_ids = {sid for c in plan.evidence for sid in c.source_ids}
        self.assertTrue(plan.steps, "expected at least one grounded step")
        for step in plan.steps:
            self.assertTrue(step.cited_fact_ids, "every step must cite a fact")
            for fid in step.cited_fact_ids:
                self.assertIn(fid, real_fact_ids, f"fabricated fact id {fid}")
            for sid in step.cited_source_ids:
                self.assertIn(sid, real_source_ids, f"fabricated source id {sid}")

    def test_grounded_plan_meets_groundedness_floor(self) -> None:
        plan = build_plan(
            complaint_id="C-ROADS",
            routing_sector="ROADS",
            routing_entity="MUN",
            complaint_text="large pothole on the main road damaging cars",
            routing_confidence=0.79,
            hitl_required=False,
            kb=self.kb,
        )
        if not plan.abstained:
            self.assertGreaterEqual(plan.groundedness, MIN_GROUNDEDNESS)
            self.assertTrue(plan.citizen_summary)

    def test_safety_sector_always_abstains_to_hitl(self) -> None:
        for sector in ABSTAIN_SECTORS:
            plan = build_plan(
                complaint_id=f"C-{sector}",
                routing_sector=sector,
                routing_entity=None,
                complaint_text="urgent issue reported by a citizen",
                routing_confidence=0.9,
                hitl_required=False,
                kb=self.kb,
            )
            self.assertTrue(plan.abstained, f"{sector} should abstain")
            self.assertTrue(plan.force_hitl, f"{sector} must force HITL")

    def test_no_kb_coverage_abstains(self) -> None:
        plan = build_plan(
            complaint_id="C-NONSENSE",
            routing_sector="WASTE",
            routing_entity="MUN",
            complaint_text="zzz qqq xkcd flibbertigibbet wibblewobble nonsensical",
            routing_confidence=0.5,
            hitl_required=False,
            kb=EntityKnowledgeBase(kb_dir="/__does_not_exist__"),
        )
        self.assertTrue(plan.abstained)
        self.assertEqual(plan.abstain_reason, "no_kb_coverage_for_complaint")

    def test_planner_is_deterministic(self) -> None:
        kwargs = dict(
            complaint_id="C-DET",
            routing_sector="WASTE",
            routing_entity="MUN",
            complaint_text="overflowing dumpster not collected",
            routing_confidence=0.8,
            hitl_required=False,
            kb=self.kb,
        )
        a = build_plan(**kwargs)
        b = build_plan(**kwargs)
        self.assertEqual(
            [s.cited_fact_ids for s in a.steps],
            [s.cited_fact_ids for s in b.steps],
        )
        self.assertEqual(a.groundedness, b.groundedness)

    def test_upstream_hitl_forces_review_even_when_grounded(self) -> None:
        plan = build_plan(
            complaint_id="C-HITL",
            routing_sector="WASTE",
            routing_entity="MUN",
            complaint_text="garbage uncollected for a week on our street",
            routing_confidence=0.8,
            hitl_required=True,
            kb=self.kb,
        )
        self.assertTrue(plan.force_hitl)


if __name__ == "__main__":
    unittest.main()
