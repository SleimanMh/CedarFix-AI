"""Tests for the CedarFix Civic Intelligence Compiler."""
from __future__ import annotations

import unittest

from src.shared.civic_compiler import (
    AutonomyLevel,
    ProofStatus,
    compile_incident_program,
)


def _base_packets() -> dict:
    iep1_signal = {
        "language": "arabizi",
        "drift_score": 0,
        "review_recommendation": "AUTO_ROUTE_ELIGIBLE",
        "classification_trace": {
            "hybrid": {
                "sector": "WATER",
                "issue_type": "PUBLIC_PIPE_LEAK",
                "confidence": 0.86,
                "reason": "rules_model_exact_agreement",
            }
        },
    }
    return {
        "complaint_id": "CF-PROOF-001",
        "text_raw": "fi may m2ata3a w fi soura masoura 3am tsarrib 7ad l tari2 bi zahle",
        "gps_lat": 33.8466,
        "gps_lon": 35.9020,
        "iep1_output": {
            "language": "arabizi",
            "drift_score": 0,
            "routing_sector": "WATER",
            "issue_type": "PUBLIC_PIPE_LEAK",
            "issue_type_confidence": 0.86,
            "iep1_signal_json": iep1_signal,
        },
        "iep1_signal_json": iep1_signal,
        "iep2_incident_json": {
            "incident_id": "INC-WATER-001",
            "cluster_size": 5,
            "incident_lifecycle_state": "EMERGING",
            "review_recommendation": "AUTO_ATTACH_TO_INCIDENT",
            "match_evidence": {
                "fusion_score": 0.91,
                "fusion_label": "same_incident",
            },
        },
        "iep3_routing_json": {
            "routing_sector": "WATER",
            "routing_entity": "BWE",
            "routing_confidence": 0.82,
            "priority_score": 65.0,
            "hitl_required": False,
            "issue_type": "PUBLIC_PIPE_LEAK",
            "issue_type_confidence": 0.86,
            "routing_risk_score": 0.12,
            "kb_location_method": "gps",
            "kb_complaint_type_id": "CT-WATER-002",
            "kb_route_reason": "sector=WATER | type=public_pipe_leak | municipality=Zahle",
            "kb_secondary_entity": "MUN",
            "shap_top3": {
                "router_version": "route_complaint_kb",
                "routing_risk_score": 0.12,
                "neuro_symbolic_trace": {
                    "ai_layer": "iep1_model_and_confidence",
                    "symbolic_layer": "route_complaint_kb",
                    "safety_layer": "hitl_gates_and_risk_model",
                },
            },
        },
        "image_fusion_json": {
            "available": True,
            "image_label": "water_leak",
            "image_sector": "WATER",
            "image_confidence": 0.91,
            "fusion": {
                "agreement": "agree",
                "confidence_delta": 0.1,
                "force_hitl": False,
                "reason": "image_text_agree:WATER",
            },
        },
        "iep4_explanation_json": {
            "evidence_refs": {
                "kb_fact_ids": ["BWE-F001"],
                "kb_source_ids": ["SRC-BWE-001"],
            },
            "guardrails": {
                "unsupported_sla_blocked": True,
                "invented_agency_blocked": True,
            },
            "verifier": {
                "allowed_fact_ids": ["BWE-F001"],
                "allowed_source_ids": ["SRC-BWE-001"],
                "no_unverified_deadline": True,
            },
        },
        "iep8_resolution_json": {
            "groundedness": 1.0,
            "top_retrieval_score": 0.41,
            "abstained": False,
            "evidence": [
                {
                    "fact_id": "BWE-F001",
                    "source_ids": ["SRC-BWE-001"],
                }
            ],
        },
        "lifecycle_json": {"reopened": False, "reopen_count": 0},
        "calibration_json": {"sector": "WATER", "ece": 0.07},
    }


class TestCivicCompiler(unittest.TestCase):
    def test_source_grounded_program_can_auto_route_with_audit(self) -> None:
        program = compile_incident_program(**_base_packets())

        self.assertEqual(
            program.autonomy_decision.level,
            AutonomyLevel.AUTO_ROUTE_WITH_AUDIT,
        )
        self.assertEqual(program.scoreboard["proof_satisfaction_rate"], 1.0)
        self.assertIn("BWE-F001", program.dsl)
        self.assertIn("civic_compiler_proof_governor", program.scoreboard["ai_layers_used"])
        self.assertEqual(program.belief_state["routing"]["entity"], "BWE")

    def test_image_text_conflict_blocks_autonomy_and_creates_question(self) -> None:
        packets = _base_packets()
        packets["image_fusion_json"] = {
            "available": True,
            "image_label": "pothole",
            "image_sector": "ROADS",
            "image_confidence": 0.93,
            "fusion": {
                "agreement": "conflict",
                "confidence_delta": -0.1,
                "force_hitl": True,
                "reason": "image_text_conflict:text=WATER,image=ROADS",
            },
        }

        program = compile_incident_program(**packets)
        obligations = {item.id: item for item in program.proof_obligations}

        self.assertEqual(obligations["PO-MODALITY"].status, ProofStatus.BLOCKED)
        self.assertEqual(
            program.autonomy_decision.level,
            AutonomyLevel.HUMAN_INVESTIGATE,
        )
        self.assertIn("Q-MODALITY", {item.id for item in program.active_sensing})
        self.assertIn("CF-IMAGE", {item.id for item in program.counterfactual_routes})

    def test_missing_source_grounding_blocks_auto_route(self) -> None:
        packets = _base_packets()
        packets["iep4_explanation_json"] = {
            "evidence_refs": {},
            "guardrails": {"unsupported_sla_blocked": True},
            "verifier": {"no_unverified_deadline": True},
        }
        packets["iep8_resolution_json"] = {
            "groundedness": 0.0,
            "top_retrieval_score": 0.0,
            "abstained": True,
            "evidence": [],
        }

        program = compile_incident_program(**packets)
        obligations = {item.id: item for item in program.proof_obligations}

        self.assertEqual(obligations["PO-SOURCE"].status, ProofStatus.BLOCKED)
        self.assertEqual(
            program.autonomy_decision.level,
            AutonomyLevel.HUMAN_INVESTIGATE,
        )
        self.assertIn("Q-SOURCE", {item.id for item in program.active_sensing})


if __name__ == "__main__":
    unittest.main()
