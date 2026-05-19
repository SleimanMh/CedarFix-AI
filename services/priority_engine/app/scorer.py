"""
Rule-based priority scorer.
Backend Engineer: Replace with ML classifier when labeled data is available.

SCORING LOGIC:
  base_score = complaint_type_weight
  + cluster_size_boost
  + visual_severity_boost
  + location_risk_boost
  Normalized to [0, 1], mapped to SeverityLevel
"""

from cedarfix_shared.schemas import PriorityResult, SeverityLevel, ComplaintType
from typing import Optional, List

# Base risk score per complaint type
TYPE_BASE_SCORE = {
    "flooding":           0.8,
    "electricity_outage": 0.7,
    "road_damage":        0.6,
    "pothole":            0.5,
    "traffic_light":      0.6,
    "waste_accumulation": 0.4,
    "water_pipe":         0.65,
    "streetlight":        0.45,
    "sidewalk_damage":    0.35,
    "other":              0.3,
}

# Districts with historically higher infrastructure risk
HIGH_RISK_DISTRICTS = {"tripoli", "tyre", "sidon", "baabda", "jounieh"}
MEDIUM_RISK_DISTRICTS = {"hamra", "ashrafieh", "verdun", "cola"}

VISUAL_SEVERITY_SCORES = {
    "CRITICAL": 0.4,
    "HIGH":     0.3,
    "MEDIUM":   0.15,
    "LOW":      0.0,
}


class PriorityScorer:
    def score(
        self,
        complaint_id: str,
        complaint_type: Optional[str],
        cluster_size: int,
        visual_severity: str,
        location_district: Optional[str],
        top_similarity_score: float,
    ) -> PriorityResult:

        factors = []

        # 1. Base score from complaint type
        base = TYPE_BASE_SCORE.get(complaint_type or "other", 0.3)
        factors.append(f"Type '{complaint_type}' base score: {base:.2f}")

        # 2. Cluster size boost (recurring = more urgent)
        cluster_boost = min(cluster_size * 0.05, 0.3)
        if cluster_size > 0:
            factors.append(f"Cluster size {cluster_size} adds {cluster_boost:.2f}")

        # 3. Visual severity boost
        visual_boost = VISUAL_SEVERITY_SCORES.get(visual_severity, 0.0)
        if visual_boost > 0:
            factors.append(f"Visual severity '{visual_severity}' adds {visual_boost:.2f}")

        # 4. Location risk boost
        district_lower = (location_district or "").lower()
        if district_lower in HIGH_RISK_DISTRICTS:
            location_boost = 0.15
            factors.append(f"High-risk district '{location_district}'")
        elif district_lower in MEDIUM_RISK_DISTRICTS:
            location_boost = 0.08
            factors.append(f"Medium-risk district '{location_district}'")
        else:
            location_boost = 0.0

        raw_score = min(base + cluster_boost + visual_boost + location_boost, 1.0)
        severity = self._map_severity(raw_score)

        return PriorityResult(
            complaint_id=complaint_id,
            severity=severity,
            priority_score=round(raw_score, 3),
            urgency_factors=factors,
            cluster_size_factor=round(cluster_boost, 3),
            visual_severity_factor=round(visual_boost, 3),
            complaint_type_factor=round(base, 3),
            location_risk_factor=round(location_boost, 3),
            confidence=0.75,  # Rule-based: fixed confidence; ML model will improve this
            processing_ms=0,
        )

    def _map_severity(self, score: float) -> SeverityLevel:
        if score >= 0.8:
            return SeverityLevel.CRITICAL
        elif score >= 0.6:
            return SeverityLevel.HIGH
        elif score >= 0.4:
            return SeverityLevel.MEDIUM
        return SeverityLevel.LOW
