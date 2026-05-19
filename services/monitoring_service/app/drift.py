"""Drift detection logic. MLOps Engineer owns this."""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cedarfix:cedarfix_secret@postgres:5432/cedarfix")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


async def compute_drift_metrics() -> dict:
    """
    Compute:
    - routing_accuracy_7d: (total - corrections) / total for last 7 days
    - admin_correction_rate: corrections in last 7 days / total in last 7 days
    - embedding_drift: placeholder (implement KL divergence in stretch)
    """
    try:
        with Session() as session:
            # Complaints in last 7 days
            result = session.execute(text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status = 'corrected' THEN 1 ELSE 0 END) as corrected
                FROM complaints
                WHERE created_at >= NOW() - INTERVAL '7 days'
            """))
            row = result.mappings().first()
            total = row["total"] or 0
            corrected = row["corrected"] or 0

            accuracy = round((total - corrected) / total, 4) if total > 0 else 1.0
            correction_rate = round(corrected / total, 4) if total > 0 else 0.0

            # Average routing confidence (proxy for model health)
            conf_result = session.execute(text("""
                SELECT AVG(routing_confidence) as avg_conf
                FROM complaints
                WHERE created_at >= NOW() - INTERVAL '7 days'
                  AND routing_confidence IS NOT NULL
            """))
            avg_conf = conf_result.scalar() or 0.0

            return {
                "routing_accuracy_7d": accuracy,
                "admin_correction_rate": correction_rate,
                "avg_routing_confidence_7d": round(float(avg_conf), 4),
                "total_complaints_7d": total,
                "corrected_complaints_7d": corrected,
                "embedding_drift": 0.0,  # TODO: implement KL divergence
                "drift_alert": correction_rate > 0.15,
            }
    except Exception as e:
        return {"error": str(e), "drift_alert": False}
