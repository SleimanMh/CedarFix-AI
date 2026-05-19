"""
Seed Data Generator — CedarFix AI
====================================
Generates 500 synthetic Lebanese infrastructure complaints.
Run this AFTER docker-compose up to populate the system with test data.

Usage:
  python scripts/seed_data.py --count 500 --submit

This script calls the Gateway API directly so all IEPs are exercised.
Data covers all complaint types, all 3 languages, multiple districts.
"""

import argparse
import random
import json
import httpx
import time

GATEWAY_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Synthetic data templates per language and complaint type
# ---------------------------------------------------------------------------

COMPLAINTS = {
    "pothole": {
        "en": [
            "There is a large pothole on the main road near the supermarket, it is dangerous for cars.",
            "Deep pothole blocking part of the road in {district}, needs urgent repair.",
            "The road on {street} has multiple potholes causing tire damage.",
        ],
        "ar": [
            "يوجد حفرة كبيرة في الطريق الرئيسية بالقرب من {district}، خطيرة جداً على السيارات.",
            "حفرة عميقة في طريق {district} تسبب أضراراً للمركبات، تحتاج إصلاحاً عاجلاً.",
            "الطريق في منطقة {district} مليء بالحفر ويشكل خطراً على المارة.",
        ],
        "fr": [
            "Il y a un grand nid de poule sur la route principale à {district}, dangereux pour les voitures.",
            "Nid de poule profond bloquant une partie de la route à {district}.",
        ],
    },
    "flooding": {
        "en": [
            "The street in {district} is completely flooded after the rain, cars cannot pass.",
            "Severe flooding near {street} intersection, water level is rising.",
        ],
        "ar": [
            "شارع {district} مغمور بالمياه بعد الأمطار، السيارات لا تستطيع المرور.",
            "فيضان شديد قرب تقاطع {street}، مستوى المياه في ارتفاع.",
        ],
        "fr": [
            "La rue à {district} est complètement inondée après la pluie.",
        ],
    },
    "electricity_outage": {
        "en": [
            "Power has been out in {district} for 3 days, no response from EDL.",
            "Electricity outage affecting the entire neighborhood in {district}.",
        ],
        "ar": [
            "انقطع التيار الكهربائي عن منطقة {district} منذ 3 أيام دون أي استجابة.",
            "انقطاع الكهرباء يؤثر على الحي بأكمله في {district}.",
        ],
        "fr": [
            "Panne d'électricité à {district} depuis 3 jours, aucune réponse d'EDL.",
        ],
    },
    "waste_accumulation": {
        "en": [
            "Garbage has not been collected in {district} for 2 weeks, causing health hazard.",
            "Overflowing trash bins on {street}, terrible smell and flies.",
        ],
        "ar": [
            "لم يتم جمع النفايات في {district} منذ أسبوعين، مما يشكل خطراً صحياً.",
            "صناديق القمامة ممتلئة في {street} وتسبب رائحة كريهة.",
        ],
        "fr": [
            "Les ordures n'ont pas été collectées à {district} depuis 2 semaines.",
        ],
    },
    "traffic_light": {
        "en": [
            "Traffic light at {street} intersection is broken and flashing randomly.",
            "The signal light at {district} main intersection has been off for a week.",
        ],
        "ar": [
            "إشارة المرور عند تقاطع {street} معطلة وتومض بشكل عشوائي.",
            "إشارة الضوء عند التقاطع الرئيسي في {district} مطفأة منذ أسبوع.",
        ],
        "fr": [
            "Le feu de signalisation à l'intersection de {street} est en panne.",
        ],
    },
    "road_damage": {
        "en": [
            "Large cracks appearing on the road surface in {district}, dangerous for motorcycles.",
            "The road on {street} is severely damaged after the recent storms.",
        ],
        "ar": [
            "تشققات كبيرة ظهرت على سطح الطريق في {district}، خطيرة على الدراجات النارية.",
            "الطريق في {street} تضرر بشدة بعد العواصف الأخيرة.",
        ],
        "fr": [
            "De grandes fissures apparaissent sur la chaussée à {district}.",
        ],
    },
    "streetlight": {
        "en": [
            "Street lights are out in {district}, the area is completely dark at night.",
            "Multiple broken street lamps on {street} creating a safety risk.",
        ],
        "ar": [
            "إنارة الشوارع في {district} مطفأة، المنطقة مظلمة تماماً في الليل.",
        ],
        "fr": [
            "Les lampadaires sont éteints à {district}, zone dangereuse la nuit.",
        ],
    },
    "water_pipe": {
        "en": [
            "Water pipe burst on {street}, water flooding the sidewalk for 2 days.",
            "Visible water leak from underground pipe near {district} area.",
        ],
        "ar": [
            "انفجر أنبوب مياه في {street}، المياه تغمر الرصيف منذ يومين.",
        ],
        "fr": [
            "Une conduite d'eau a éclaté sur {street}, eau sur le trottoir depuis 2 jours.",
        ],
    },
}

DISTRICTS = [
    "Hamra", "Cola", "Jounieh", "Tripoli", "Sidon", "Tyre",
    "Ashrafieh", "Verdun", "Baabda", "Dekwaneh", "Jdeideh",
    "Antelias", "Jbeil", "Kaslik",
]

STREETS = [
    "Corniche", "Bliss Street", "Rue Gouraud", "Sassine Square",
    "Airport Road", "Charles Helou Avenue", "Spears Street",
]

DISTRICT_COORDS = {
    "Hamra":      (33.8956, 35.4784),
    "Cola":       (33.8731, 35.4942),
    "Jounieh":    (33.9815, 35.6179),
    "Tripoli":    (34.4367, 35.8497),
    "Sidon":      (33.5631, 35.3714),
    "Tyre":       (33.2706, 35.2038),
    "Ashrafieh":  (33.8891, 35.5133),
    "Verdun":     (33.8855, 35.4841),
    "Baabda":     (33.8342, 35.5506),
    "Dekwaneh":   (33.8760, 35.5540),
    "Jdeideh":    (33.8927, 35.5698),
    "Antelias":   (33.9133, 35.5937),
    "Jbeil":      (34.1205, 35.6500),
    "Kaslik":     (33.9831, 35.6124),
}


def generate_complaint(complaint_type: str) -> dict:
    district = random.choice(DISTRICTS)
    street = random.choice(STREETS)
    lang = random.choice(list(COMPLAINTS[complaint_type].keys()))

    templates = COMPLAINTS[complaint_type][lang]
    text = random.choice(templates).format(district=district, street=street)

    lat, lng = DISTRICT_COORDS.get(district, (33.8886, 35.4955))
    # Add small random offset to avoid identical coordinates
    lat += random.uniform(-0.01, 0.01)
    lng += random.uniform(-0.01, 0.01)

    return {
        "text": text,
        "latitude": round(lat, 6),
        "longitude": round(lng, 6),
        "district": district,
        "address_hint": f"{street}, {district}",
    }


def submit_complaint(client: httpx.Client, data: dict) -> dict:
    resp = client.post(
        f"{GATEWAY_URL}/complaints",
        data=data,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Seed CedarFix AI with synthetic complaints")
    parser.add_argument("--count", type=int, default=100, help="Number of complaints to generate")
    parser.add_argument("--submit", action="store_true", help="Actually submit to API")
    parser.add_argument("--output", type=str, default=None, help="Save to JSON file")
    args = parser.parse_args()

    complaint_types = list(COMPLAINTS.keys())
    generated = []

    for i in range(args.count):
        ctype = complaint_types[i % len(complaint_types)]
        complaint = generate_complaint(ctype)
        generated.append(complaint)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(generated, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(generated)} complaints to {args.output}")

    if args.submit:
        print(f"Submitting {len(generated)} complaints to {GATEWAY_URL}...")
        success = 0
        errors = 0
        with httpx.Client() as client:
            for i, complaint in enumerate(generated):
                try:
                    result = submit_complaint(client, complaint)
                    success += 1
                    if (i + 1) % 10 == 0:
                        print(f"  [{i+1}/{len(generated)}] ✓ {result.get('complaint_id', '?')[:8]}... "
                              f"type={result.get('complaint_type')} "
                              f"severity={result.get('severity')} "
                              f"entity={result.get('assigned_entity', '?')[:30]}")
                except Exception as e:
                    errors += 1
                    print(f"  [{i+1}] ERROR: {e}")
                time.sleep(0.2)  # Don't overwhelm the gateway

        print(f"\nDone. Success: {success}, Errors: {errors}")
    else:
        print(f"Generated {len(generated)} complaints (dry run). Use --submit to send to API.")
        for c in generated[:5]:
            print(f"  Sample: {c['text'][:80]}...")


if __name__ == "__main__":
    main()
