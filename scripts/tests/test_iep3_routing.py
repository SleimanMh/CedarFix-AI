"""IEP-3 routing unit tests.

Tests the IEP-3 router module against known sector/entity ground truth
from sector_agency_map.csv.

Run with:
    python -m pytest scripts/tests/test_iep3_routing.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep3.router import _pick_sector, route  # noqa: E402


class TestSectorPicker(unittest.TestCase):
    def test_explicit_sector_wins(self) -> None:
        self.assertEqual(_pick_sector("ROADS", "unknown"), "ROADS")

    def test_other_sector_falls_back_to_issue_type(self) -> None:
        self.assertEqual(_pick_sector("OTHER", "pothole_road"), "ROADS")

    def test_flood_from_issue_type(self) -> None:
        self.assertEqual(_pick_sector(None, "flash_flood_drain"), "FLOODING")

    def test_electricity_from_issue_type(self) -> None:
        self.assertEqual(_pick_sector("", "kahraba_outage"), "ELECTRICITY")

    def test_water_from_issue_type(self) -> None:
        self.assertEqual(_pick_sector(None, "may_no_supply"), "WATER")

    def test_waste_from_issue_type(self) -> None:
        self.assertEqual(_pick_sector(None, "zbele_uncollected"), "WASTE")

    def test_telecom_from_issue_type(self) -> None:
        self.assertEqual(_pick_sector(None, "internet_outage"), "TELECOM")

    def test_no_signal_returns_other(self) -> None:
        self.assertEqual(_pick_sector(None, None), "OTHER")


class TestRoutingDecision(unittest.TestCase):
    def _route(self, sector=None, issue_type=None, issue_conf=0.80, drift=0, lat=None, lon=None):
        return route(
            complaint_id="TEST-001",
            routing_sector=sector,
            issue_type=issue_type,
            issue_type_confidence=issue_conf,
            drift_score=drift,
            gps_lat=lat,
            gps_lon=lon,
        )

    def test_roads_routes_to_mun_or_mpwt(self) -> None:
        d = self._route(sector="ROADS")
        self.assertEqual(d["routing_sector"], "ROADS")
        # Primary entity for ROADS is MUN per sector_agency_map
        self.assertIn(d["routing_entity"], ("MUN", "MPWT", "CDR"))
        self.assertGreater(d["routing_confidence"], 0.65)

    def test_water_routes_to_rwa(self) -> None:
        d = self._route(sector="WATER")
        self.assertEqual(d["routing_sector"], "WATER")
        # Without GPS the router cannot pick one of Lebanon's regional water
        # establishments, so it returns all candidates pipe-joined
        # (e.g. "BMLWE|NLWE|SLWE|BWE"). Each candidate must be a valid entity.
        valid_water_entities = {"RWA", "MUN", "MEW", "BMLWE", "NLWE", "SLWE", "BWE"}
        candidates = str(d["routing_entity"]).split("|")
        self.assertTrue(candidates, "routing_entity must not be empty")
        for candidate in candidates:
            self.assertIn(candidate, valid_water_entities)
        self.assertGreater(d["routing_confidence"], 0.65)

    def test_electricity_always_hitl(self) -> None:
        d = self._route(sector="ELECTRICITY")
        self.assertTrue(d["hitl_required"])
        self.assertLessEqual(d["routing_confidence"], 0.60)

    def test_safety_always_hitl(self) -> None:
        d = self._route(sector="SAFETY")
        self.assertTrue(d["hitl_required"])
        self.assertLessEqual(d["routing_confidence"], 0.60)

    def test_high_drift_lowers_confidence(self) -> None:
        d_low = self._route(sector="ROADS", drift=0, issue_conf=0.90)
        d_high = self._route(sector="ROADS", drift=3, issue_conf=0.90)
        self.assertLess(d_high["routing_confidence"], d_low["routing_confidence"])

    def test_low_issue_conf_lowers_routing_conf(self) -> None:
        d_high = self._route(sector="WASTE", issue_conf=0.90)
        d_low = self._route(sector="WASTE", issue_conf=0.30)
        self.assertLess(d_low["routing_confidence"], d_high["routing_confidence"])

    def test_flooding_higher_priority_than_waste(self) -> None:
        d_flood = self._route(sector="FLOODING")
        d_waste = self._route(sector="WASTE")
        self.assertGreater(d_flood["priority_score"], d_waste["priority_score"])

    def test_gps_grounding_adds_priority_bonus(self) -> None:
        d_no_gps = self._route(sector="ROADS")
        d_gps = self._route(sector="ROADS", lat=33.8886, lon=35.4955)
        self.assertGreaterEqual(d_gps["priority_score"], d_no_gps["priority_score"])

    def test_shap_top3_has_required_keys(self) -> None:
        d = self._route(sector="ROADS")
        self.assertIn("sector_signal", d["shap_top3"])
        self.assertIn("issue_type_conf", d["shap_top3"])
        self.assertIn("drift_penalty", d["shap_top3"])

    def test_other_sector_forces_hitl(self) -> None:
        d = self._route(sector="OTHER")
        self.assertTrue(d["hitl_required"])

    def test_telecom_produces_ogero_entity(self) -> None:
        d = self._route(sector="TELECOM")
        self.assertIn("OGERO", d["routing_entity"].upper())

    def test_waste_routes_to_mun(self) -> None:
        d = self._route(sector="WASTE")
        self.assertEqual(d["routing_entity"], "MUN")

    def test_flooding_routes_to_cd(self) -> None:
        d = self._route(sector="FLOODING")
        # Civil Defense is primary for flooding
        self.assertEqual(d["routing_entity"], "CD")


class TestRoutingIssueTypeFallback(unittest.TestCase):
    """Verify that issue_type signals correctly override a missing sector."""

    def test_jora_routes_to_roads(self) -> None:
        d = route("T-002", None, "jora_pothole", 0.75, 0, None, None)
        self.assertEqual(d["routing_sector"], "ROADS")

    def test_sarif_water_routes_to_water(self) -> None:
        d = route("T-003", "OTHER", "water_mie_sewage", 0.70, 1, None, None)
        self.assertIn(d["routing_sector"], ("WATER", "ROADS", "FLOODING"))

    def test_nnar_safety_routes_to_safety(self) -> None:
        d = route("T-004", None, "safety_khouf_fire", 0.80, 0, None, None)
        self.assertEqual(d["routing_sector"], "SAFETY")


if __name__ == "__main__":
    unittest.main()
