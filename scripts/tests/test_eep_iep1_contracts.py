from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.eep.models import ComplaintRequest
from src.eep.pii import scrub_pii
from src.iep1.extractor import extract


class EEPRequestContractTests(unittest.TestCase):
    def test_language_hint_is_normalized_and_limited(self) -> None:
        payload = ComplaintRequest(
            text="fi jora kbire 3al tari2",
            gps_lat=33.8897,
            gps_lon=35.48,
            language_hint="ARABIZI",
        )
        self.assertEqual(payload.language_hint, "arabizi")

        with self.assertRaises(ValidationError):
            ComplaintRequest(text="fi jora kbire", language_hint="spanish")

    def test_gps_must_be_pair_and_inside_lebanon(self) -> None:
        with self.assertRaises(ValidationError):
            ComplaintRequest(text="fi jora kbire 3al tari2", gps_lat=33.8897)

        with self.assertRaises(ValidationError):
            ComplaintRequest(
                text="fi jora kbire 3al tari2",
                gps_lat=48.8566,
                gps_lon=2.3522,
            )

    def test_image_must_be_real_jpeg_or_png_base64(self) -> None:
        tiny_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8).decode()
        payload = ComplaintRequest(text="broken drain in Hamra", image_b64=tiny_png)
        self.assertEqual(payload.image_b64, tiny_png)

        with self.assertRaises(ValidationError):
            ComplaintRequest(text="broken drain in Hamra", image_b64="not-base64")

        fake_payload = base64.b64encode(b"GIF89a").decode()
        with self.assertRaises(ValidationError):
            ComplaintRequest(text="broken drain in Hamra", image_b64=fake_payload)

    def test_pii_scrubber_removes_phone_and_email(self) -> None:
        scrubbed = scrub_pii("Call me on +961 3 123 456 or user@example.com about this")
        self.assertNotIn("+961", scrubbed)
        self.assertNotIn("user@example.com", scrubbed)
        self.assertIn("[PHONE]", scrubbed)
        self.assertIn("[EMAIL]", scrubbed)


class IEP1ExtractionContractTests(unittest.TestCase):
    def test_pothole_with_high_risk_modifier_preserves_specific_issue(self) -> None:
        result = extract("demo-1", "fi jora kbire 3al tari2 w l wad3 m5atra ktir", "arabizi", include_embedding=False)
        self.assertEqual(result["routing_sector"], "ROADS")
        self.assertEqual(result["issue_type"], "POTHOLE")
        self.assertGreaterEqual(result["drift_score"], 2)

    def test_transformer_code_switch_routes_to_transformer_fault(self) -> None:
        result = extract(
            "demo-2",
            "transformateur m7arrak bi borj 7ammoud w fi ri7et 7ar2",
            "mixed",
            include_embedding=False,
        )
        self.assertEqual(result["routing_sector"], "ELECTRICITY")
        self.assertEqual(result["issue_type"], "TRANSFORMER_FAULT")
        self.assertGreaterEqual(result["drift_score"], 2)

    def test_sewage_ambiguity_preserves_water_issue(self) -> None:
        result = extract("demo-3", "may ws5a w ri7et sarif 3al tari2 bi bliss", "arabizi", include_embedding=False)
        self.assertEqual(result["routing_sector"], "WATER")
        self.assertEqual(result["issue_type"], "SEWAGE_OVERFLOW")
        self.assertGreaterEqual(result["drift_score"], 2)


if __name__ == "__main__":
    unittest.main()
