from __future__ import annotations

import base64

from PIL import Image


def test_image_to_base64_resizes_and_encodes(import_service_module):
    analyzer = import_service_module("image_understanding", "app.analyzer", ml=True)
    encoded = analyzer._image_to_base64(Image.new("RGB", (1200, 600), "red"), max_size=128)
    assert base64.b64decode(encoded).startswith(b"\xff\xd8")


def test_label_parsing_helpers(import_service_module):
    analyzer = import_service_module("image_understanding", "app.analyzer", ml=True)
    assert analyzer._snake("Low Hanging Wire!") == "low_hanging_wire"
    assert analyzer._float("1.8") == 1.0
    assert analyzer._float("bad", 0.25) == 0.25
    assert analyzer._infer_failure_mode("low-hanging cable crossing a road") == "low_hanging"
    assert analyzer._is_component_mismatch("low_hanging_cable", "water_pipe") is True


def test_parse_visual_candidates_deduplicates_repairs_and_falls_back(import_service_module):
    analyzer = import_service_module("image_understanding", "app.analyzer", ml=True)
    candidates = analyzer._parse_visual_candidates(
        {
            "visual_candidates": [
                {
                    "visual_category": "utilities",
                    "visual_subcategory": "damaged_road",
                    "physical_component": "power line",
                    "failure_mode": "hanging low",
                    "caption": "A sagging wire crosses the street",
                    "confidence": 0.8,
                },
                {
                    "visual_category": "utilities",
                    "visual_subcategory": "damaged_road",
                    "physical_component": "power line",
                    "confidence": 0.7,
                },
            ]
        }
    )
    assert len(candidates) == 1
    assert candidates[0].semantic_domain == "utilities"
    assert candidates[0].failure_mode == "low_hanging"
    assert "power_line" in candidates[0].visual_subcategory

    fallback = analyzer._parse_visual_candidates({"visual_category": "roads", "confidence": "bad"})
    assert fallback[0].visual_category == "roads"
    assert fallback[0].confidence == 0.5

