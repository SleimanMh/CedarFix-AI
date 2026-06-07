#!/usr/bin/env python3
"""
Seed Municipality Lookup
========================
Reads the prepared municipality lookup JSON/JSONL and upserts municipality
routing profiles into:

  - PostgreSQL  → municipality_lookup table
  - Qdrant      → "municipality_lookup" collection (768-dim, same model
                   as routing_knowledge)

The script is idempotent: re-running upserts without duplicating rows.

Usage:
  # Ensure the monitoring stack is running (postgres + qdrant)
  python scripts/seed_municipality_lookup.py

  # Override paths / connection:
  MUNICIPALITY_LOOKUP_DOCS=/path/to/all_1064.jsonl \\
  DATABASE_URL=postgresql://user:pass@host:5432/db \\
  QDRANT_HOST=localhost \\
  python scripts/seed_municipality_lookup.py

Environment variables:
  MUNICIPALITY_LOOKUP_DOCS — path to enriched municipality lookup JSON/JSONL
                             (default: RAG Data/municipality/
                                      municipality_lookup_compiled_production.json)
  DATABASE_URL             — PostgreSQL DSN
  QDRANT_HOST              — Qdrant host (default: localhost)
  QDRANT_PORT              — Qdrant port (default: 6333)
  MODEL_NAME               — sentence-transformers model
                             (default: paraphrase-multilingual-mpnet-base-v2)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = (
    REPO_ROOT
    / "RAG Data"
    / "municipality"
    / "municipality_lookup_compiled_production.json"
)

QDRANT_COLLECTION = "municipality_lookup"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _load_docs(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8-sig")
    stripped = raw.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        loaded = json.loads(raw)
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
        docs.append(doc)
    return docs


def _doc_id(doc: dict) -> str:
    """Stable UUID from the doc id field (e.g. municipality:M1)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, doc["id"]))


def _flat(doc: dict) -> dict[str, Any]:
    """Flatten the lean municipality lookup doc for DB/Qdrant insert."""
    loc     = doc.get("location", {})
    names   = doc.get("names", {})
    routing = doc.get("routing", {})
    contact = doc.get("contact", {})

    # Backward-compatible fallbacks for older packs.
    evidence = doc.get("evidence", {})
    source_url = (doc.get("source_url") or "").strip()
    if not source_url:
        source_url = (evidence.get("source_url") or "").strip()
    if not source_url:
        source_urls = evidence.get("source_urls") or []
        if source_urls:
            source_url = str(source_urls[0]).strip()

    record_status = (doc.get("record_status") or "").strip()
    if not record_status:
        if doc.get("registry_id"):
            record_status = "matched"
        else:
            record_status = "unmatched"

    return {
        "id":                          doc.get("id") or f"municipality:{doc.get('municipality_id', '')}",
        "version":                     doc.get("version", "current"),
        "doc_type":                    doc.get("doc_type", "municipality_lookup_profile"),
        "municipality_id":             doc.get("municipality_id", ""),
        "coverage_universe_id":        doc.get("coverage_universe_id") or None,
        "registry_id":                 doc.get("registry_id") or None,
        "record_status":               record_status,
        # names
        "name_en":                     (names.get("english") or "").strip() or None,
        "name_ar":                     (names.get("arabic") or "").strip() or None,
        # location
        "governorate":                 (loc.get("governorate") or "").strip() or None,
        "district":                    (loc.get("district") or "").strip() or None,
        "pcode":                       (loc.get("pcode") or "").strip() or None,
        "latitude":                    _float_or_none(loc.get("latitude")),
        "longitude":                   _float_or_none(loc.get("longitude")),
        # routing policy
        "can_auto_route":              bool(routing.get("can_auto_route", False)),
        "blind_auto_submit_allowed":   bool(routing.get("blind_auto_submit_allowed", False)),
        "user_confirmation_required":  bool(routing.get("user_confirmation_required", True)),
        "scope_disclosure_required":   bool(routing.get("scope_disclosure_required", True)),
        "routing_decision":            (routing.get("routing_decision") or "").strip() or None,
        "route_permission_tier":       (routing.get("route_permission_tier") or "").strip() or None,
        # contact
        "phone":                       (contact.get("phone") or "").strip() or None,
        "email":                       (contact.get("email") or "").strip() or None,
        "website_or_social_url":       (contact.get("website_or_social_url") or "").strip() or None,
        "endpoint_level":              (contact.get("endpoint_level") or "").strip() or None,
        "preferred_contact_or_endpoint": (
            contact.get("preferred_contact_or_endpoint") or ""
        ).strip() or None,
        "source_url":                  source_url or None,
        # retrieval
        "retrieval_text":              doc.get("retrieval_text") or "",
    }


def _float_or_none(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    configured = os.getenv("MUNICIPALITY_LOOKUP_DOCS")
    docs_path = Path(configured).resolve() if configured else DEFAULT_DOCS

    if not docs_path.exists():
        print(
            f"ERROR: enriched JSONL not found at {docs_path}\n"
            "Run scripts/compile_routing_knowledge.py or set MUNICIPALITY_LOOKUP_DOCS."
        )
        sys.exit(1)

    print(f"Loading municipality docs: {docs_path}")
    docs = _load_docs(docs_path)
    print(f"  {len(docs)} documents loaded")

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://cedarfix:cedarfix_secret@localhost:5432/cedarfix",
    )
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = _env_int("QDRANT_PORT", 6333)
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY") or None
    qdrant_timeout = _env_int("QDRANT_TIMEOUT", 120)
    qdrant_prefer_grpc = _env_bool("QDRANT_PREFER_GRPC", False)
    model_name  = os.getenv(
        "MODEL_NAME",
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    )

    # ── Embedding model ──────────────────────────────────────────────────────
    print(f"Loading embedding model: {model_name}")
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer(model_name)
        dim = model.get_sentence_embedding_dimension()
        print(f"  → dimension: {dim}")
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("  pip install sentence-transformers")
        sys.exit(1)

    # ── Qdrant ────────────────────────────────────────────────────────────────
    print(f"Connecting to Qdrant at {qdrant_url or f'{qdrant_host}:{qdrant_port}'}")
    try:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams, PointStruct  # type: ignore
        if qdrant_url:
            qdrant = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=qdrant_timeout,
                prefer_grpc=qdrant_prefer_grpc,
            )
        else:
            qdrant = QdrantClient(
                host=qdrant_host,
                port=qdrant_port,
                grpc_port=_env_int("QDRANT_GRPC_PORT", 6334),
                api_key=qdrant_api_key,
                timeout=qdrant_timeout,
                prefer_grpc=qdrant_prefer_grpc,
            )
    except ImportError:
        print("ERROR: qdrant-client not installed.")
        print("  pip install qdrant-client")
        sys.exit(1)

    existing_collections = [c.name for c in qdrant.get_collections().collections]
    if QDRANT_COLLECTION not in existing_collections:
        print(f"Creating Qdrant collection: {QDRANT_COLLECTION}")
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        print(f"Qdrant collection '{QDRANT_COLLECTION}' already exists — will upsert")

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    print(f"Connecting to PostgreSQL: {database_url[:50]}...")
    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
    except ImportError:
        print("ERROR: psycopg2 not installed.")
        print("  pip install psycopg2-binary")
        sys.exit(1)

    # Ensure table exists (idempotent — init.sql may already have created it)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS municipality_lookup (
            id                          VARCHAR(120) PRIMARY KEY,
            version                     VARCHAR(20)  DEFAULT 'current',
            doc_type                    VARCHAR(60)  DEFAULT 'municipality_lookup_profile',
            municipality_id             VARCHAR(40)  NOT NULL,
            coverage_universe_id        VARCHAR(60),
            registry_id                 VARCHAR(60),
            record_status               VARCHAR(20)  DEFAULT 'unmatched',
            name_en                     VARCHAR(300),
            name_ar                     VARCHAR(300),
            governorate                 VARCHAR(100),
            district                    VARCHAR(100),
            pcode                       VARCHAR(20),
            latitude                    FLOAT,
            longitude                   FLOAT,
            can_auto_route              BOOLEAN      DEFAULT FALSE,
            blind_auto_submit_allowed   BOOLEAN      DEFAULT FALSE,
            user_confirmation_required  BOOLEAN      DEFAULT TRUE,
            scope_disclosure_required   BOOLEAN      DEFAULT TRUE,
            routing_decision            VARCHAR(120),
            route_permission_tier       VARCHAR(80),
            phone                       VARCHAR(200),
            email                       VARCHAR(300),
            website_or_social_url       VARCHAR(600),
            endpoint_level              VARCHAR(60),
            preferred_contact_or_endpoint VARCHAR(300),
            source_url                  VARCHAR(1000),
            retrieval_text              TEXT,
            qdrant_point_id             VARCHAR(50),
            updated_at                  TIMESTAMP    DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mun_lookup_municipality_id ON municipality_lookup(municipality_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mun_lookup_registry_id     ON municipality_lookup(registry_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mun_lookup_can_auto_route  ON municipality_lookup(can_auto_route)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mun_lookup_governorate     ON municipality_lookup(governorate)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mun_lookup_district        ON municipality_lookup(district)")
    conn.commit()

    # ── Embed + upsert ────────────────────────────────────────────────────────
    points = []
    print(f"\nEmbedding and seeding {len(docs)} municipality docs...\n")

    for doc in docs:
        flat = _flat(doc)
        point_id = _doc_id(doc)

        retrieval_text = flat["retrieval_text"] or flat["name_en"] or flat["municipality_id"]
        embedding = model.encode(retrieval_text, normalize_embeddings=True).tolist()

        # PostgreSQL upsert
        cur.execute("""
            INSERT INTO municipality_lookup
                (id, version, doc_type, municipality_id, coverage_universe_id,
                 registry_id, record_status, name_en, name_ar, governorate, district,
                 pcode, latitude, longitude, can_auto_route, blind_auto_submit_allowed,
                 user_confirmation_required, scope_disclosure_required, routing_decision,
                 route_permission_tier, phone, email, website_or_social_url,
                 endpoint_level, preferred_contact_or_endpoint, source_url, retrieval_text,
                 qdrant_point_id, updated_at)
            VALUES
                (%s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                district                    = EXCLUDED.district,
                registry_id                 = EXCLUDED.registry_id,
                record_status               = EXCLUDED.record_status,
                phone                       = EXCLUDED.phone,
                email                       = EXCLUDED.email,
                website_or_social_url       = EXCLUDED.website_or_social_url,
                can_auto_route              = EXCLUDED.can_auto_route,
                routing_decision            = EXCLUDED.routing_decision,
                source_url                  = EXCLUDED.source_url,
                retrieval_text              = EXCLUDED.retrieval_text,
                qdrant_point_id             = EXCLUDED.qdrant_point_id,
                updated_at                  = NOW()
        """, (
            flat["id"], flat["version"], flat["doc_type"], flat["municipality_id"],
            flat["coverage_universe_id"], flat["registry_id"], flat["record_status"],
            flat["name_en"], flat["name_ar"], flat["governorate"], flat["district"],
            flat["pcode"], flat["latitude"], flat["longitude"],
            flat["can_auto_route"], flat["blind_auto_submit_allowed"],
            flat["user_confirmation_required"], flat["scope_disclosure_required"],
            flat["routing_decision"], flat["route_permission_tier"],
            flat["phone"], flat["email"], flat["website_or_social_url"],
            flat["endpoint_level"], flat["preferred_contact_or_endpoint"],
            flat["source_url"], flat["retrieval_text"], point_id,
        ))

        # Qdrant payload — all fields that are useful for metadata filtering
        payload = {
            "doc_id":                     flat["id"],
            "municipality_id":            flat["municipality_id"],
            "registry_id":                flat["registry_id"],
            "record_status":              flat["record_status"],
            "name_en":                    flat["name_en"],
            "name_ar":                    flat["name_ar"],
            "governorate":                flat["governorate"],
            "district":                   flat["district"],
            "can_auto_route":             flat["can_auto_route"],
            "blind_auto_submit_allowed":  flat["blind_auto_submit_allowed"],
            "user_confirmation_required": flat["user_confirmation_required"],
            "routing_decision":           flat["routing_decision"],
            "phone":                      flat["phone"],
            "email":                      flat["email"],
            "source_url":                 flat["source_url"],
            "doc_type":                   flat["doc_type"],
            "version":                    flat["version"],
        }

        points.append(PointStruct(id=point_id, vector=embedding, payload=payload))
        label = flat["name_en"] or flat["municipality_id"]
        auto = "AUTO" if flat["can_auto_route"] else "fallback"
        district_tag = flat["district"] or "no-district"
        print(f"  ✓ {flat['municipality_id']:12s}  {label[:30]:30s}  {auto:8s}  dist={district_tag}")

    conn.commit()
    cur.close()
    conn.close()
    print("\nPostgreSQL inserts committed.")

    # Bulk upload into Qdrant. The municipality dataset is large enough that a
    # single blocking upsert can hit HTTP read timeouts on local/k8s Qdrant.
    upload_batch_size = _env_int("MUNICIPALITY_QDRANT_UPLOAD_BATCH_SIZE", 128)
    upload_parallel = _env_int("MUNICIPALITY_QDRANT_UPLOAD_PARALLEL", 2)
    upload_retries = _env_int("MUNICIPALITY_QDRANT_UPLOAD_MAX_RETRIES", 5)
    upload_wait = _env_bool("MUNICIPALITY_QDRANT_UPLOAD_WAIT", False)
    print(
        f"Bulk uploading {len(points)} points to Qdrant collection '{QDRANT_COLLECTION}' "
        f"(batch_size={upload_batch_size}, parallel={upload_parallel}, "
        f"max_retries={upload_retries}, wait={upload_wait})..."
    )
    qdrant.upload_points(
        collection_name=QDRANT_COLLECTION,
        points=points,
        batch_size=upload_batch_size,
        parallel=upload_parallel,
        max_retries=upload_retries,
        wait=upload_wait,
    )
    print(f"Qdrant bulk upload submitted {len(points)} points into '{QDRANT_COLLECTION}'.")

    if _env_bool("QDRANT_VERIFY_AFTER_UPLOAD", True):
        try:
            info = qdrant.get_collection(QDRANT_COLLECTION)
            print(
                f"\nQdrant collection '{QDRANT_COLLECTION}': {info.points_count} points, "
                f"dim={info.config.params.vectors.size}"
            )
        except Exception as exc:
            print(f"\nWARNING: Qdrant upload was submitted, but verification read failed: {type(exc).__name__}: {exc}")
            print("         Re-run with QDRANT_VERIFY_AFTER_UPLOAD=false to skip this read on slow Qdrant.")
    print("\nSeeding complete.")
    print("Next: run scripts/test_municipality_disambiguation.py to validate.")


if __name__ == "__main__":
    main()
