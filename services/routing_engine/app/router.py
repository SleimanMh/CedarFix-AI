"""
Rule-based complaint router.
Backend Engineer: Replace with ML classifier trained on admin-corrected data.

ROUTING LOGIC:
  Complaint type → primary candidate entity
  District/location → refine candidate (EDL vs municipality for streetlights, etc.)
  Confidence: rule matches = 0.90, partial match = 0.72, no match = 0.50 → human review
"""

from cedarfix_shared.schemas import RoutingResult, RoutingEntity
from typing import Optional, List


# Maps complaint_type → (primary_entity, secondary_entity, base_confidence)
TYPE_TO_ENTITY = {
    "pothole":            (RoutingEntity.MINISTRY_PUBLIC_WORKS,    RoutingEntity.BEIRUT_MUNICIPALITY,  0.88),
    "road_damage":        (RoutingEntity.MINISTRY_PUBLIC_WORKS,    RoutingEntity.BEIRUT_MUNICIPALITY,  0.88),
    "flooding":           (RoutingEntity.MINISTRY_ENVIRONMENT,     RoutingEntity.MINISTRY_PUBLIC_WORKS, 0.82),
    "water_pipe":         (RoutingEntity.WATER_AUTHORITY,          RoutingEntity.BEIRUT_MUNICIPALITY,  0.90),
    "electricity_outage": (RoutingEntity.EDL,                      None,                               0.95),
    "telecom_outage":    (RoutingEntity.OGERO,                    None,                               0.95),
    "streetlight":        (RoutingEntity.EDL,                      RoutingEntity.BEIRUT_MUNICIPALITY,  0.80),
    "traffic_light":      (RoutingEntity.INTERNAL_SECURITY,        RoutingEntity.BEIRUT_MUNICIPALITY,  0.85),
    "waste_accumulation": (RoutingEntity.BEIRUT_MUNICIPALITY,      RoutingEntity.MINISTRY_ENVIRONMENT, 0.87),
    "sidewalk_damage":    (RoutingEntity.BEIRUT_MUNICIPALITY,      RoutingEntity.MINISTRY_PUBLIC_WORKS, 0.83),
    "other":              (RoutingEntity.HUMAN_REVIEW,             None,                               0.40),
}

# District → municipality override
DISTRICT_MUNICIPALITY = {
    "tripoli":            RoutingEntity.NORTH_MUNICIPALITY,
    "north lebanon":      RoutingEntity.NORTH_MUNICIPALITY,
    "sidon":              RoutingEntity.SOUTH_MUNICIPALITY,
    "tyre":               RoutingEntity.SOUTH_MUNICIPALITY,
    "south lebanon":      RoutingEntity.SOUTH_MUNICIPALITY,
    "jounieh":            RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "jbeil":              RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "byblos":             RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "mount lebanon":      RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
}


class ComplaintRouter:
    def __init__(self, auto_threshold: float, review_threshold: float):
        self.auto_threshold = auto_threshold
        self.review_threshold = review_threshold

    def route(
        self,
        complaint_id: str,
        complaint_type: Optional[str],
        severity: Optional[str],
        location_district: Optional[str],
        location_mentions: List[str],
        keywords: List[str],
    ) -> RoutingResult:

        rationale = []
        complaint_type = complaint_type or "other"

        primary, secondary, base_confidence = TYPE_TO_ENTITY.get(
            complaint_type, TYPE_TO_ENTITY["other"]
        )
        rationale.append(f"Complaint type '{complaint_type}' → {primary}")

        # Override for non-Beirut districts
        district = (location_district or "").lower()
        for mention in [district] + [m.lower() for m in location_mentions]:
            if mention in DISTRICT_MUNICIPALITY:
                municipality = DISTRICT_MUNICIPALITY[mention]
                # Only override if primary was a Beirut entity
                if primary in (RoutingEntity.BEIRUT_MUNICIPALITY,):
                    primary = municipality
                    base_confidence *= 0.95
                    rationale.append(f"District '{mention}' overrides to {municipality}")
                break

        auto_routed = base_confidence >= self.auto_threshold
        requires_review = base_confidence < self.review_threshold

        if requires_review:
            primary = RoutingEntity.HUMAN_REVIEW
            rationale.append("Low confidence → Human Review Queue")

        return RoutingResult(
            complaint_id=complaint_id,
            primary_entity=primary,
            primary_confidence=round(base_confidence, 3),
            secondary_entity=secondary,
            secondary_confidence=round(base_confidence * 0.6, 3) if secondary else 0.0,
            routing_rationale=rationale,
            auto_routed=auto_routed,
            requires_review=requires_review,
            processing_ms=0,
        )
