"""IEP-8 grounded-resolution benchmark.

Turns "we added grounded RAG" into *measured* evidence. The benchmark runs the
full retrieve→synthesise→verify→decide pipeline over a labelled fixture and
asserts the three properties that matter for a public-sector co-pilot:

- **Zero hallucinated citations** across every case — every cited fact_id /
  source_id in every issued plan exists in that plan's retrieved evidence.
- **Grounded cases** are issued, route to the right entity family, and clear
  the groundedness floor.
- **Abstain cases** (life-safety sectors, no-coverage) are withheld and
  escalated to human review.

Deterministic; no model weights or network. Fixture:
``data/eval/resolution_grounding_eval_v1.jsonl``.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.iep8.planner import build_plan
from src.iep8.retriever import get_kb
from src.shared.resolution_schemas import MIN_GROUNDEDNESS

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "eval"
    / "resolution_grounding_eval_v1.jsonl"
)


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    with _FIXTURE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


class TestGroundingBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.kb = get_kb()
        cls.cases = _load_cases()
        cls.plans = {
            c["id"]: build_plan(
                complaint_id=c["id"],
                routing_sector=c["sector"],
                routing_entity=c["entity"],
                complaint_text=c["query"],
                routing_confidence=0.8,
                hitl_required=False,
                kb=cls.kb,
            )
            for c in cls.cases
        }

    def test_fixture_is_non_trivial(self) -> None:
        self.assertGreaterEqual(len(self.cases), 12)
        self.assertTrue(any(c["expect_abstain"] for c in self.cases))
        self.assertTrue(any(not c["expect_abstain"] for c in self.cases))

    def test_zero_hallucinated_citations_across_all_cases(self) -> None:
        """The headline guarantee: no plan ever cites a fact it didn't retrieve."""
        for case in self.cases:
            plan = self.plans[case["id"]]
            real_fact_ids = {c.fact_id for c in plan.evidence}
            real_source_ids = {sid for c in plan.evidence for sid in c.source_ids}
            for step in plan.steps:
                for fid in step.cited_fact_ids:
                    self.assertIn(fid, real_fact_ids, f"{case['id']}: fabricated fact {fid}")
                for sid in step.cited_source_ids:
                    self.assertIn(sid, real_source_ids, f"{case['id']}: fabricated source {sid}")

    def test_abstain_cases_escalate_to_human(self) -> None:
        for case in self.cases:
            if not case["expect_abstain"]:
                continue
            plan = self.plans[case["id"]]
            self.assertTrue(plan.abstained, f"{case['id']} should abstain")
            self.assertTrue(plan.force_hitl, f"{case['id']} must force HITL")

    def test_grounded_cases_are_issued_and_routed(self) -> None:
        for case in self.cases:
            if case["expect_abstain"]:
                continue
            plan = self.plans[case["id"]]
            self.assertFalse(plan.abstained, f"{case['id']} should be issued")
            self.assertGreaterEqual(
                plan.groundedness,
                min(case["min_groundedness"], MIN_GROUNDEDNESS),
                f"{case['id']} below groundedness floor",
            )
            self.assertTrue(plan.steps, f"{case['id']} should have steps")
            self.assertTrue(plan.citizen_summary, f"{case['id']} should have a summary")
            top_entity = plan.evidence[0].entity_id
            self.assertIn(
                top_entity,
                case["expected_top_entities"],
                f"{case['id']} top entity {top_entity} not in {case['expected_top_entities']}",
            )

    def test_issued_plans_carry_citations(self) -> None:
        issued = [self.plans[c["id"]] for c in self.cases if not c["expect_abstain"]]
        for plan in issued:
            self.assertTrue(plan.evidence, f"{plan.complaint_id} should retrieve evidence")
            self.assertTrue(
                all(s.cited_fact_ids for s in plan.steps),
                f"{plan.complaint_id} has an uncited step",
            )


if __name__ == "__main__":
    unittest.main()
