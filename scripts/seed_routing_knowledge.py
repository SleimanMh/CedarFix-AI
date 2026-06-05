#!/usr/bin/env python3
"""
Seed Routing Knowledge Base
============================
Inserts Lebanese public-sector routing documents into:
  - PostgreSQL  → routing_knowledge table (metadata + description)
  - Qdrant      → "routing_knowledge" collection (768-dim embeddings)

Usage:
    python scripts/compile_routing_knowledge.py
    python scripts/validate_routing_knowledge.py
    python scripts/seed_routing_knowledge.py

Requirements (run inside or alongside the running stack):
    pip install psycopg2-binary qdrant-client sentence-transformers

Environment variables (defaults match docker-compose.yml):
    DATABASE_URL  — PostgreSQL connection string
    QDRANT_HOST   — Qdrant host (default: localhost)
    QDRANT_PORT   — Qdrant port (default: 6333)
    ROUTING_KNOWLEDGE_DOCS — compiled JSONL path or JSON array path

The script is idempotent: re-running it upserts documents without creating
duplicates (it deletes and re-inserts by doc_id).
"""

import json
import os
import uuid
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPILED_DOCS = REPO_ROOT / "RAG Data" / "compiled" / "routing_knowledge_docs.jsonl"

# ---------------------------------------------------------------------------
# Routing knowledge documents
# ---------------------------------------------------------------------------

# Each entry maps to ONE (entity, responsibility_area) pair.
# Embedding text is built from: description + keywords + complaint_types.
# Keep descriptions factual and specific to Lebanese public sector context.

ROUTING_DOCS = [

    # ── Ministry of Public Works and Transport (MoPW) ────────────────────────
    {
        "doc_id": "mopw-roads",
        "entity_name": "Ministry of Public Works",
        "entity_enum": "Ministry of Public Works",
        "entity_type": "ministry",
        "short_name": "MoPW",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["pothole", "road_damage", "sidewalk_damage", "flooding"],
        "keywords": [
            "highway", "national road", "autoroute", "bridge", "tunnel",
            "CDR", "asphalt", "road repair", "inter-city", "freeway",
            "طريق", "جسر", "نفق", "autoroute", "route nationale",
        ],
        "not_responsible_for": ["electricity", "water", "internet", "garbage", "municipal streets"],
        "description": (
            "The Ministry of Public Works and Transport is responsible for all national "
            "highways, inter-city roads, bridges, and tunnels across Lebanon. "
            "The Council for Development and Reconstruction (CDR) executes many large-scale "
            "road projects on the Ministry's behalf. Municipal streets within Beirut city limits "
            "are handled by Beirut Municipality, not this Ministry. Complaints about potholes "
            "on national highways (e.g., Dahr el Baydar, Nahr el Kalb, coastal highway) "
            "belong here."
        ),
        "confidence_prior": 0.88,
        "hotline": "01-455610",
    },
    {
        "doc_id": "cdr-projects",
        "entity_name": "Council for Development and Reconstruction",
        "entity_enum": "Council for Development and Reconstruction",
        "entity_type": "ministry",
        "short_name": "CDR",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["road_damage", "pothole", "flooding", "sidewalk_damage"],
        "keywords": [
            "CDR", "reconstruction", "highway project", "infrastructure project",
            "LINORD", "coastal highway", "north highway", "south highway",
            "مجلس الإنماء والإعمار",
        ],
        "not_responsible_for": ["electricity", "water", "garbage", "municipal streets", "traffic incidents"],
        "description": (
            "The Council for Development and Reconstruction (CDR) implements major national "
            "infrastructure projects including highways, bridges, and public works across Lebanon. "
            "CDR is the execution arm for large MoPW projects. It does not handle routine "
            "pothole repairs on local streets, but is responsible for faults on CDR-managed roads "
            "such as the coastal highway, north/south corridors, and major bridges."
        ),
        "confidence_prior": 0.82,
        "hotline": "01-981460",
    },

    # ── Beirut Municipality ──────────────────────────────────────────────────
    {
        "doc_id": "bm-roads",
        "entity_name": "Beirut Municipality",
        "entity_enum": "Beirut Municipality",
        "entity_type": "municipality",
        "short_name": "BM",
        "governs_nationally": False,
        "governorates": ["Beirut Governorate"],
        "districts": ["Beirut"],
        "municipalities": ["Beirut"],
        "complaint_types": ["pothole", "road_damage", "sidewalk_damage", "flooding"],
        "keywords": [
            "Beirut", "Hamra", "Verdun", "Ashrafieh", "Gemmayzeh", "Mar Mikhael",
            "Cola", "Corniche", "Badaro", "Ras Beirut", "Zarif", "Downtown",
            "Tallet el Khayat", "Sanayeh", "Msaytbeh", "Furn el Chebbak",
            "بيروت", "حمرا", "الأشرفية", "الجميزة",
        ],
        "not_responsible_for": ["electricity", "internet", "national highway", "water pipes"],
        "description": (
            "Beirut Municipality is responsible for all streets, sidewalks, drainage, and local "
            "infrastructure within Beirut city administrative boundaries. This covers all Beirut "
            "neighbourhoods: Hamra, Verdun, Ashrafieh, Gemmayzeh, Mar Mikhael, Corniche, Downtown, "
            "Badaro, Cola, Zarif, Ras Beirut, Tallet el Khayat, Sanayeh, and all other areas "
            "within Beirut city limits. Waste collection in Beirut city also falls under BM."
        ),
        "confidence_prior": 0.90,
        "hotline": "1735",
    },
    {
        "doc_id": "bm-waste",
        "entity_name": "Beirut Municipality",
        "entity_enum": "Beirut Municipality",
        "entity_type": "municipality",
        "short_name": "BM",
        "governs_nationally": False,
        "governorates": ["Beirut Governorate"],
        "districts": ["Beirut"],
        "municipalities": ["Beirut"],
        "complaint_types": ["waste_accumulation"],
        "keywords": [
            "garbage", "waste", "trash", "bins", "دفان", "garbage pile", "Beirut waste",
            "overflowing bin", "النفايات", "القمامة", "zbele",
        ],
        "not_responsible_for": ["recycling", "industrial waste", "outside Beirut"],
        "description": (
            "Beirut Municipality manages household and street waste collection within Beirut city. "
            "Overflowing bins, uncollected garbage, and illegal dumping on Beirut streets are handled "
            "by BM. Industrial or large-scale illegal dumping in nature areas is handled by the "
            "Ministry of Environment."
        ),
        "confidence_prior": 0.88,
        "hotline": "1735",
    },

    # ── Electricité du Liban (EDL) ────────────────────────────────────────────
    {
        "doc_id": "edl-electricity",
        "entity_name": "Electricite Du Liban",
        "entity_enum": "Electricite Du Liban",
        "entity_type": "utility",
        "short_name": "EDL",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["electricity_outage"],
        "keywords": [
            "electricity", "power", "blackout", "EDL", "كهرباء", "cut", "no power",
            "power outage", "electric failure", "generator", "انقطاع الكهرباء",
            "electricite", "courant", "current",
        ],
        "not_responsible_for": ["roads", "water", "internet", "private generators"],
        "description": (
            "Electricité du Liban (EDL) is the state electricity utility responsible for power "
            "generation and distribution across Lebanon. EDL handles electricity outages, faulty "
            "electrical infrastructure, and downed power lines nationwide. Private generator "
            "companies are separate from EDL. EDL has regional offices throughout Lebanon."
        ),
        "confidence_prior": 0.95,
        "hotline": "1530",
    },
    {
        "doc_id": "edl-streetlights",
        "entity_name": "Electricite Du Liban",
        "entity_enum": "Electricite Du Liban",
        "entity_type": "utility",
        "short_name": "EDL",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["streetlight"],
        "keywords": [
            "street light", "streetlight", "lamp post", "dark street", "street lamp",
            "إنارة", "عمود كهرباء", "lampadaire", "éclairage public",
        ],
        "not_responsible_for": ["roads", "water", "internet", "traffic lights"],
        "description": (
            "Broken or non-functional public street lights are handled by Electricité du Liban (EDL) "
            "in coordination with municipalities. EDL provides the power; municipalities may own "
            "the lamp posts. For Beirut street lighting, coordinate with both EDL and Beirut Municipality."
        ),
        "confidence_prior": 0.82,
        "hotline": "1530",
    },

    # ── Ogero ─────────────────────────────────────────────────────────────────
    {
        "doc_id": "ogero-telecom",
        "entity_name": "Ogero",
        "entity_enum": "Ogero",
        "entity_type": "utility",
        "short_name": "Ogero",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["telecom_outage"],
        "keywords": [
            "internet", "wifi", "DSL", "ADSL", "fiber", "broadband", "Ogero",
            "landline", "phone line", "telephone", "أوجيرو", "internet outage",
            "no internet", "slow internet", "fibres optiques",
        ],
        "not_responsible_for": ["mobile data", "electricity", "water", "roads", "garbage"],
        "description": (
            "Ogero is the Lebanese state telecom operator responsible for fixed-line internet "
            "(DSL, fiber), landline telephone infrastructure, and backbone connectivity. "
            "Ogero handles outages and damage to DSL/fiber infrastructure nationwide. "
            "Mobile network issues (Alfa, Touch) are NOT handled by Ogero."
        ),
        "confidence_prior": 0.95,
        "hotline": "1515",
    },

    # ── Water Establishments ──────────────────────────────────────────────────
    {
        "doc_id": "water-beirut-mt-lebanon",
        "entity_name": "Beirut Water Authority",
        "entity_enum": "Beirut Water Authority",
        "entity_type": "utility",
        "short_name": "BWE",
        "governs_nationally": False,
        "governorates": ["Beirut Governorate", "Mount Lebanon Governorate"],
        "districts": ["Beirut", "Metn", "Keserwan", "Chouf", "Aley", "Baabda", "Jbeil"],
        "municipalities": [],
        "complaint_types": ["water_pipe", "flooding"],
        "keywords": [
            "water", "pipe", "leak", "burst pipe", "water pressure", "no water",
            "sewage", "drainage", "مياه", "أنابيب", "تسرب مياه",
            "eau", "fuite d'eau", "Beirut water", "Mount Lebanon water",
        ],
        "not_responsible_for": ["electricity", "internet", "garbage", "roads"],
        "description": (
            "The Beirut and Mount Lebanon Water Establishment handles water supply, water pipe "
            "maintenance, and sewage infrastructure for Beirut city and all of Mount Lebanon "
            "governorate (Metn, Keserwan, Chouf, Aley, Baabda, Jbeil districts). "
            "Burst pipes, water leaks, low water pressure, and sewer overflows in these areas "
            "are their responsibility."
        ),
        "confidence_prior": 0.90,
        "hotline": "01-581520",
    },
    {
        "doc_id": "water-north",
        "entity_name": "North Lebanon Water Establishment",
        "entity_enum": "North Lebanon Water Establishment",
        "entity_type": "utility",
        "short_name": "NLWE",
        "governs_nationally": False,
        "governorates": ["North Governorate", "Akkar Governorate"],
        "districts": ["Tripoli", "Zgharta", "Batroun", "Koura", "Bcharre", "Minieh-Danniyeh", "Akkar"],
        "municipalities": [],
        "complaint_types": ["water_pipe", "flooding"],
        "keywords": [
            "Tripoli water", "North Lebanon water", "Batroun water", "Zgharta water",
            "Akkar water", "مياه الشمال", "water pipe", "pipe leak",
        ],
        "not_responsible_for": ["electricity", "internet", "garbage", "roads"],
        "description": (
            "The North Lebanon Water Establishment manages water supply and sewage for the "
            "North governorate and Akkar governorate, covering Tripoli, Zgharta, Batroun, "
            "Koura, Bcharre, Minieh-Danniyeh, and all Akkar districts."
        ),
        "confidence_prior": 0.88,
        "hotline": "06-430222",
    },
    {
        "doc_id": "water-south",
        "entity_name": "South Lebanon Water Establishment",
        "entity_enum": "South Lebanon Water Establishment",
        "entity_type": "utility",
        "short_name": "SLWE",
        "governs_nationally": False,
        "governorates": ["South Governorate", "Nabatieh Governorate"],
        "districts": ["Sidon", "Tyre", "Jezzine", "Nabatieh", "Bint Jbeil", "Marjayoun", "Hasbaya"],
        "municipalities": [],
        "complaint_types": ["water_pipe", "flooding"],
        "keywords": [
            "Sidon water", "Tyre water", "South Lebanon water", "Nabatieh water",
            "مياه الجنوب", "water pipe south", "Saida water",
        ],
        "not_responsible_for": ["electricity", "internet", "garbage", "roads"],
        "description": (
            "The South Lebanon Water Establishment manages water supply and sewage for the "
            "South governorate (Sidon, Tyre, Jezzine) and Nabatieh governorate "
            "(Nabatieh, Bint Jbeil, Marjayoun, Hasbaya)."
        ),
        "confidence_prior": 0.88,
        "hotline": "07-722233",
    },
    {
        "doc_id": "water-bekaa",
        "entity_name": "Bekaa Water Establishment",
        "entity_enum": "Bekaa Water Establishment",
        "entity_type": "utility",
        "short_name": "BeWE",
        "governs_nationally": False,
        "governorates": ["Bekaa Governorate", "Baalbek-Hermel Governorate"],
        "districts": ["Zahle", "Western Bekaa", "Rachaya", "Baalbek", "Hermel"],
        "municipalities": [],
        "complaint_types": ["water_pipe", "flooding"],
        "keywords": [
            "Zahle water", "Bekaa water", "Baalbek water", "مياه البقاع",
            "water pipe Bekaa", "Chtaura water",
        ],
        "not_responsible_for": ["electricity", "internet", "garbage", "roads"],
        "description": (
            "The Bekaa Water Establishment manages water supply and sewage for the Bekaa "
            "governorate (Zahle, Western Bekaa, Rachaya) and Baalbek-Hermel governorate."
        ),
        "confidence_prior": 0.88,
        "hotline": "08-820227",
    },

    # ── Internal Security Forces (ISF) ───────────────────────────────────────
    {
        "doc_id": "isf-traffic",
        "entity_name": "Internal Security Forces",
        "entity_enum": "Internal Security Forces",
        "entity_type": "security",
        "short_name": "ISF",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["traffic_incident", "traffic_light", "public_safety"],
        "keywords": [
            "accident", "crash", "ISF", "police", "traffic police", "road block",
            "dangerous driver", "رقبال", "قوى الأمن", "traffic signal",
            "traffic management", "congestion police", "accident scene",
        ],
        "not_responsible_for": ["pothole repair", "electricity", "water", "garbage", "road maintenance"],
        "description": (
            "The Internal Security Forces (ISF) Traffic Department handles road accidents, "
            "traffic congestion emergencies, public safety incidents, and broken traffic signals "
            "that pose immediate danger. ISF has jurisdiction nationwide. They respond first and "
            "coordinate with municipalities for traffic light repairs. Public safety threats, "
            "vandalism of infrastructure, and any emergency requiring police presence go to ISF."
        ),
        "confidence_prior": 0.90,
        "hotline": "112",
    },

    # ── Ministry of Environment ───────────────────────────────────────────────
    {
        "doc_id": "moe-environment",
        "entity_name": "Ministry of Environment",
        "entity_enum": "Ministry of Environment",
        "entity_type": "ministry",
        "short_name": "MoE",
        "governs_nationally": True,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["waste_accumulation", "flooding"],
        "keywords": [
            "illegal dumping", "pollution", "chemical waste", "industrial waste",
            "river pollution", "sea pollution", "open burning", "asbestos",
            "وزارة البيئة", "تلوث", "نفايات صلبة", "environmental violation",
            "nature", "forest", "protected area",
        ],
        "not_responsible_for": ["household garbage", "roads", "electricity", "water pipes"],
        "description": (
            "The Ministry of Environment handles environmental violations: illegal dumping in "
            "nature or on roadsides, industrial or chemical waste, river and sea pollution, "
            "open burning of waste, and any complaint in protected natural areas. "
            "Household garbage collection in cities is handled by municipalities, not MoE. "
            "MoE is the correct entity for large-scale illegal dumping outside urban areas."
        ),
        "confidence_prior": 0.82,
        "hotline": "01-976555",
    },

    # ── Generic Municipality Fallback ────────────────────────────────────────
    {
        "doc_id": "generic-municipality",
        "entity_name": "Local Municipality",
        "entity_enum": "Local Municipality",
        "entity_type": "municipality",
        "short_name": "LocalMun",
        "governs_nationally": False,
        "governorates": [],
        "districts": [],
        "municipalities": [],
        "complaint_types": ["pothole", "road_damage", "waste_accumulation", "sidewalk_damage", "flooding", "streetlight"],
        "keywords": [
            "local street", "municipal road", "neighborhood", "village road",
            "local municipality", "بلدية", "بلدة", "قرية",
        ],
        "not_responsible_for": ["national highways", "electricity", "water", "internet"],
        "description": (
            "For complaints about local streets, sidewalks, and waste collection in areas outside "
            "Beirut city, the responsible entity is the local municipality of that town or village. "
            "Lebanon has over 1,000 municipalities. Use this as a fallback when the specific "
            "municipality is not identified and the complaint is clearly about local (non-national) "
            "infrastructure in a residential area."
        ),
        "confidence_prior": 0.65,
        "hotline": None,
    },
]


# ---------------------------------------------------------------------------
# Load compiled documents and build embedding text
# ---------------------------------------------------------------------------


def _load_compiled_docs(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    stripped = raw.lstrip()
    if not stripped:
        return []

    if stripped.startswith("["):
        try:
            loaded = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"{path}: invalid JSON array: {exc}") from exc
        if not isinstance(loaded, list):
            raise ValueError(f"{path}: expected a JSON array of documents")
        docs: list[dict[str, Any]] = []
        for idx, item in enumerate(loaded, 1):
            if not isinstance(item, dict):
                raise ValueError(f"{path}: item {idx} is not a JSON object")
            docs.append(item)
        return docs

    docs: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except Exception as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        docs.append(doc)
    return docs


def _routing_docs() -> list[dict[str, Any]]:
    configured = os.getenv("ROUTING_KNOWLEDGE_DOCS")
    path = Path(configured).resolve() if configured else DEFAULT_COMPILED_DOCS
    if path.exists():
        print(f"Loading compiled routing knowledge: {path}")
        return _load_compiled_docs(path)
    print("WARNING: compiled routing knowledge file not found; using legacy hardcoded ROUTING_DOCS")
    return ROUTING_DOCS


def _build_embedding_text(doc: dict) -> str:
    parts = [
        doc["description"],
        f"Entity: {doc['entity_name']}",
        f"Document type: {doc.get('doc_type', 'responsibility')}",
        f"Route mode: {doc.get('route_mode', 'routing_candidate')}",
        f"Route authority: {doc.get('route_authority', 'authoritative')}",
        f"Retrieval stage: {doc.get('retrieval_stage', 'stage1_dispatch')}",
        f"Retrieval lane: {doc.get('retrieval_lane', 'unknown')}",
        f"Source reliability: {doc.get('source_reliability', 'unknown')}",
        f"Complaint types: {', '.join(doc['complaint_types'])}",
        f"Keywords: {', '.join(doc['keywords'][:30])}",
    ]
    if doc.get("governorates"):
        parts.append(f"Geographic scope: {', '.join(doc['governorates'])}")
    if doc.get("districts"):
        parts.append(f"Districts: {', '.join(doc['districts'][:5])}")
    if doc.get("municipalities"):
        parts.append(f"Municipalities: {', '.join(doc['municipalities'][:5])}")
    if doc.get("not_responsible_for"):
        parts.append(f"Not responsible for: {', '.join(doc['not_responsible_for'][:12])}")
    if doc.get("exact_match_terms"):
        parts.append(f"Exact match terms: {', '.join(doc['exact_match_terms'][:20])}")
    if doc.get("negative_signals"):
        parts.append(f"Negative signals: {', '.join(doc['negative_signals'][:20])}")
    if doc.get("hitl_conditions"):
        parts.append(f"Human review conditions: {', '.join(doc['hitl_conditions'][:10])}")
    if doc.get("source_ids"):
        parts.append(f"Source ids: {', '.join(doc['source_ids'][:10])}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://cedarfix:cedarfix_secret@localhost:5432/cedarfix",
    )
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    collection_name = os.getenv("ROUTING_QDRANT_COLLECTION", "routing_knowledge")
    embedding_model = os.getenv(
        "MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    )
    routing_docs = _routing_docs()

    print(f"Loading embedding model: {embedding_model}")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(embedding_model)
        dim = model.get_sentence_embedding_dimension()
        print(f"  → dimension: {dim}")
    except ImportError:
        print("ERROR: sentence-transformers not installed. Run: pip install sentence-transformers")
        sys.exit(1)

    print(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port}")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
        qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
    except ImportError:
        print("ERROR: qdrant-client not installed. Run: pip install qdrant-client")
        sys.exit(1)

    # Create or recreate Qdrant collection
    existing = [c.name for c in qdrant.get_collections().collections]
    if collection_name not in existing:
        print(f"Creating Qdrant collection: {collection_name}")
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        print(f"Qdrant collection '{collection_name}' already exists — will upsert")

    print(f"Connecting to PostgreSQL: {database_url[:50]}...")
    try:
        import psycopg2
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    # Ensure routing_knowledge table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routing_knowledge (
            id              VARCHAR(255) PRIMARY KEY,
            entity_name     VARCHAR(100) NOT NULL,
            entity_enum     VARCHAR(100) NOT NULL,
            entity_type     VARCHAR(30),
            short_name      VARCHAR(20),
            governs_nat     BOOLEAN DEFAULT FALSE,
            governorates    JSONB DEFAULT '[]',
            districts       JSONB DEFAULT '[]',
            municipalities  JSONB DEFAULT '[]',
            complaint_types JSONB DEFAULT '[]',
            keywords        JSONB DEFAULT '[]',
            not_responsible JSONB DEFAULT '[]',
            description     TEXT,
            confidence_prior FLOAT DEFAULT 0.85,
            hotline         VARCHAR(50),
            source_ids      JSONB DEFAULT '[]',
            source_files    JSONB DEFAULT '[]',
            hitl_conditions JSONB DEFAULT '[]',
            last_reviewed   VARCHAR(20),
            source_profile  VARCHAR(50),
            doc_type        VARCHAR(60) DEFAULT 'responsibility',
            route_mode      VARCHAR(80) DEFAULT 'routing_candidate',
            route_authority VARCHAR(80) DEFAULT 'authoritative',
            source_reliability VARCHAR(80) DEFAULT 'unknown',
            location_precision VARCHAR(80),
            exact_match_terms JSONB DEFAULT '[]',
            negative_signals JSONB DEFAULT '[]',
            structured_fields JSONB DEFAULT '{}',
            retrieval_weight FLOAT DEFAULT 1.0,
            retrieval_stage VARCHAR(40) DEFAULT 'stage1_dispatch',
            retrieval_lane VARCHAR(40),
            stage1_dispatch_candidate BOOLEAN DEFAULT FALSE,
            stage_priority INTEGER DEFAULT 4,
            qdrant_point_id VARCHAR(50),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE routing_knowledge ALTER COLUMN id TYPE VARCHAR(255)")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS source_ids JSONB DEFAULT '[]'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS source_files JSONB DEFAULT '[]'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS hitl_conditions JSONB DEFAULT '[]'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS last_reviewed VARCHAR(20)")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS source_profile VARCHAR(50)")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS doc_type VARCHAR(60) DEFAULT 'responsibility'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS route_mode VARCHAR(80) DEFAULT 'routing_candidate'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS route_authority VARCHAR(80) DEFAULT 'authoritative'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS source_reliability VARCHAR(80) DEFAULT 'unknown'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS location_precision VARCHAR(80)")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS exact_match_terms JSONB DEFAULT '[]'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS negative_signals JSONB DEFAULT '[]'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS structured_fields JSONB DEFAULT '{}'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS retrieval_weight FLOAT DEFAULT 1.0")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS retrieval_stage VARCHAR(40) DEFAULT 'stage1_dispatch'")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS retrieval_lane VARCHAR(40)")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS stage1_dispatch_candidate BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE routing_knowledge ADD COLUMN IF NOT EXISTS stage_priority INTEGER DEFAULT 4")
    conn.commit()

    points = []
    print(f"\nEmbedding and seeding {len(routing_docs)} documents...\n")

    for doc in routing_docs:
        embed_text = _build_embedding_text(doc)
        embedding = model.encode(embed_text, normalize_embeddings=True).tolist()

        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc["doc_id"]))

        # Upsert into PostgreSQL
        cur.execute("""
            INSERT INTO routing_knowledge
                (id, entity_name, entity_enum, entity_type, short_name,
                 governs_nat, governorates, districts, municipalities,
                 complaint_types, keywords, not_responsible, description,
                 confidence_prior, hotline, source_ids, source_files, hitl_conditions,
                 last_reviewed, source_profile, doc_type, route_mode, route_authority,
                 source_reliability, location_precision, exact_match_terms,
                 negative_signals, structured_fields, retrieval_weight,
                 retrieval_stage, retrieval_lane, stage1_dispatch_candidate, stage_priority,
                 qdrant_point_id, updated_at)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s,
                 %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                description     = EXCLUDED.description,
                complaint_types = EXCLUDED.complaint_types,
                keywords        = EXCLUDED.keywords,
                confidence_prior= EXCLUDED.confidence_prior,
                source_ids      = EXCLUDED.source_ids,
                source_files    = EXCLUDED.source_files,
                hitl_conditions = EXCLUDED.hitl_conditions,
                last_reviewed   = EXCLUDED.last_reviewed,
                source_profile  = EXCLUDED.source_profile,
                doc_type        = EXCLUDED.doc_type,
                route_mode      = EXCLUDED.route_mode,
                route_authority = EXCLUDED.route_authority,
                source_reliability = EXCLUDED.source_reliability,
                location_precision = EXCLUDED.location_precision,
                exact_match_terms = EXCLUDED.exact_match_terms,
                negative_signals = EXCLUDED.negative_signals,
                structured_fields = EXCLUDED.structured_fields,
                retrieval_weight = EXCLUDED.retrieval_weight,
                retrieval_stage = EXCLUDED.retrieval_stage,
                retrieval_lane = EXCLUDED.retrieval_lane,
                stage1_dispatch_candidate = EXCLUDED.stage1_dispatch_candidate,
                stage_priority = EXCLUDED.stage_priority,
                qdrant_point_id = EXCLUDED.qdrant_point_id,
                updated_at      = NOW()
        """, (
            doc["doc_id"],
            doc["entity_name"],
            doc["entity_enum"],
            doc["entity_type"],
            doc["short_name"],
            doc["governs_nationally"],
            json.dumps(doc.get("governorates", [])),
            json.dumps(doc.get("districts", [])),
            json.dumps(doc.get("municipalities", [])),
            json.dumps(doc["complaint_types"]),
            json.dumps(doc["keywords"]),
            json.dumps(doc.get("not_responsible_for", [])),
            doc["description"],
            doc.get("confidence_prior", 0.85),
            doc.get("hotline"),
            json.dumps(doc.get("source_ids", [])),
            json.dumps(doc.get("source_files", [])),
            json.dumps(doc.get("hitl_conditions", [])),
            doc.get("last_reviewed"),
            doc.get("source_profile", "legacy"),
            doc.get("doc_type", "responsibility"),
            doc.get("route_mode", "routing_candidate"),
            doc.get("route_authority", "authoritative"),
            doc.get("source_reliability", "unknown"),
            doc.get("location_precision"),
            json.dumps(doc.get("exact_match_terms", [])),
            json.dumps(doc.get("negative_signals", [])),
            json.dumps(doc.get("structured_fields", {})),
            doc.get("retrieval_weight", 1.0),
            doc.get("retrieval_stage", "stage1_dispatch"),
            doc.get("retrieval_lane"),
            bool(doc.get("stage1_dispatch_candidate", False)),
            int(doc.get("stage_priority", 4)),
            point_id,
        ))

        # Build Qdrant payload (excludes large embedding)
        payload = {
            "doc_id":          doc["doc_id"],
            "entity_name":     doc["entity_name"],
            "entity_enum":     doc["entity_enum"],
            "entity_type":     doc["entity_type"],
            "short_name":      doc["short_name"],
            "governs_nationally": doc["governs_nationally"],
            "governorates":    doc.get("governorates", []),
            "districts":       doc.get("districts", []),
            "municipalities":  doc.get("municipalities", []),
            "complaint_types": doc["complaint_types"],
            "keywords":        doc["keywords"][:30],
            "not_responsible_for": doc.get("not_responsible_for", []),
            "description":     doc["description"],
            "confidence_prior": doc.get("confidence_prior", 0.85),
            "hotline":         doc.get("hotline"),
            "source_ids":      doc.get("source_ids", []),
            "source_files":    doc.get("source_files", []),
            "hitl_conditions": doc.get("hitl_conditions", []),
            "hitl_always_required": doc.get("hitl_always_required", False),
            "last_reviewed":   doc.get("last_reviewed"),
            "responsibility_level": doc.get("responsibility_level", "legacy"),
            "source_entity_id": doc.get("source_entity_id"),
            "doc_type":        doc.get("doc_type", "responsibility"),
            "route_mode":      doc.get("route_mode", "routing_candidate"),
            "route_authority": doc.get("route_authority", "authoritative"),
            "source_reliability": doc.get("source_reliability", "unknown"),
            "location_precision": doc.get("location_precision"),
            "exact_match_terms": doc.get("exact_match_terms", []),
            "negative_signals": doc.get("negative_signals", []),
            "structured_fields": doc.get("structured_fields", {}),
            "retrieval_weight": doc.get("retrieval_weight", 1.0),
            "retrieval_stage": doc.get("retrieval_stage", "stage1_dispatch"),
            "retrieval_lane": doc.get("retrieval_lane"),
            "stage1_dispatch_candidate": bool(doc.get("stage1_dispatch_candidate", False)),
            "stage_priority": int(doc.get("stage_priority", 4)),
        }

        points.append(PointStruct(id=point_id, vector=embedding, payload=payload))
        print(f"  ✓ {doc['doc_id']:40s}  entity={doc['entity_name'][:35]}")

    conn.commit()
    cur.close()
    conn.close()
    print("\nPostgreSQL inserts committed.")

    # Batch upsert into Qdrant
    qdrant.upsert(collection_name=collection_name, points=points)
    print(f"Qdrant upserted {len(points)} points into '{collection_name}'.")

    # Quick verification
    info = qdrant.get_collection(collection_name)
    print(f"\nQdrant collection '{collection_name}': {info.points_count} points, "
          f"dim={info.config.params.vectors.size}")
    print("\nSeeding complete.")


if __name__ == "__main__":
    main()
