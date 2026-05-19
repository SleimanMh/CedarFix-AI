"""
End-to-end pipeline evaluation script.
Submits test complaints and measures accuracy vs. expected output.

Usage:
  python scripts/evaluate_pipeline.py
"""

import httpx
import json

GATEWAY_URL = "http://localhost:8000"

# Expected routing per complaint type (ground truth for MVP evaluation)
EXPECTED_ROUTING = {
    "electricity_outage": "Electricite Du Liban",
    "water_pipe":         "Beirut Water Authority",
    "pothole":            "Ministry of Public Works",
    "road_damage":        "Ministry of Public Works",
    "waste_accumulation": "Beirut Municipality",
    "flooding":           "Ministry of Environment",
    "traffic_light":      "Internal Security Forces",
}

TEST_CASES = [
    {"text": "The electricity has been out for 3 days in Hamra district.", "expected_type": "electricity_outage"},
    {"text": "Water pipe burst on Bliss Street, flooding the sidewalk.", "expected_type": "water_pipe"},
    {"text": "Large pothole on the main road in Ashrafieh, dangerous for cars.", "expected_type": "pothole"},
    {"text": "Garbage piling up on Cola intersection for 2 weeks.", "expected_type": "waste_accumulation"},
    {"text": "Traffic light at Sassine Square is broken.", "expected_type": "traffic_light"},
    {"text": "يوجد حفرة كبيرة في طريق الحمراء تسبب أضراراً للسيارات.", "expected_type": "pothole"},
    {"text": "انقطع التيار الكهربائي عن منطقة الأشرفية منذ يومين.", "expected_type": "electricity_outage"},
    {"text": "Nid de poule dangereux sur la route principale à Jounieh.", "expected_type": "pothole"},
]


def evaluate():
    results = []
    type_correct = 0
    routing_correct = 0

    with httpx.Client(timeout=60.0) as client:
        for tc in TEST_CASES:
            try:
                resp = client.post(f"{GATEWAY_URL}/complaints", data={"text": tc["text"]})
                resp.raise_for_status()
                decision = resp.json()

                pred_type = decision.get("complaint_type", "unknown")
                pred_entity = decision.get("assigned_entity", "unknown")
                expected_entity = EXPECTED_ROUTING.get(tc["expected_type"], "?")

                type_ok = pred_type == tc["expected_type"]
                routing_ok = pred_entity == expected_entity

                type_correct += int(type_ok)
                routing_correct += int(routing_ok)

                results.append({
                    "text": tc["text"][:60],
                    "expected_type": tc["expected_type"],
                    "predicted_type": pred_type,
                    "type_correct": type_ok,
                    "expected_entity": expected_entity,
                    "predicted_entity": pred_entity,
                    "routing_correct": routing_ok,
                    "severity": decision.get("severity"),
                    "routing_confidence": decision.get("routing_confidence"),
                })
            except Exception as e:
                print(f"ERROR on: {tc['text'][:40]}... → {e}")

    n = len(results)
    print("\n" + "="*70)
    print("CedarFix AI — Pipeline Evaluation")
    print("="*70)
    for r in results:
        status = "✓" if r["routing_correct"] else "✗"
        print(f"{status} [{r['expected_type']:20}] → {r['predicted_entity'][:35]} "
              f"(conf={r['routing_confidence']:.2f if r['routing_confidence'] else 'N/A'})")

    print(f"\nType Classification Accuracy:  {type_correct}/{n} = {type_correct/n:.1%}")
    print(f"Routing Accuracy:              {routing_correct}/{n} = {routing_correct/n:.1%}")

    with open("evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nFull results saved to evaluation_results.json")


if __name__ == "__main__":
    evaluate()
