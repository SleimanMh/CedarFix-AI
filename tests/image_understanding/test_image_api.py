from __future__ import annotations

from fastapi.testclient import TestClient

from cedarfix_shared.schemas import ImageQualityJSON, ImageUnderstandingResult, VisualUnderstandingJSON


class FakeImageModel:
    vlm_analyzer = None

    async def analyze(self, complaint_id, image_filename, complaint_text):
        return ImageUnderstandingResult(
            complaint_id=complaint_id,
            image_present=True,
            image_id=image_filename,
            image_quality=ImageQualityJSON(usable=True, quality_score=0.9),
            visual_understanding=VisualUnderstandingJSON(
                visual_category="roads",
                visual_subcategory="road_damage",
                damage_visible=True,
                confidence=0.84,
            ),
            image_embedding=[0.1, 0.2],
            clip_text_embedding=[0.3, 0.4] if complaint_text else [],
        )


def test_image_api_health_and_analyze(import_service_module, monkeypatch):
    main = import_service_module("image_understanding", "app.main", ml=True)
    monkeypatch.setattr(main, "model", FakeImageModel())
    client = TestClient(main.app)

    health = client.get("/health").json()
    assert health["service"] == "image-understanding"
    assert health["model_loaded"] is True

    response = client.post(
        "/analyze",
        json={
            "complaint_id": "c1",
            "image_filename": "local://road.jpg",
            "complaint_text": "Broken road",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["image_present"] is True
    assert payload["visual_understanding"]["visual_subcategory"] == "road_damage"
    assert payload["clip_text_embedding"] == [0.3, 0.4]
