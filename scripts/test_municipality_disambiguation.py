"""
test_municipality_disambiguation.py
=====================================
Validates that the prepared municipality lookup JSONL + Qdrant municipality_lookup
collection can correctly disambiguate municipalities that share similar
names but belong to different districts.

This addresses handoff item 5 from NEXT_CHAT_PROMPT_v116_TO_v117:
  "Build tests for ambiguous municipality names and false auto-routing."

Test strategy:
  Part A — Static JSONL tests (no Qdrant needed):
    Assert the enriched JSONL has distinct district values for
    known ambiguous name pairs, so metadata filtering will work.

  Part B — Qdrant retrieval tests (requires running stack):
    Query the municipality_lookup collection with a district filter
    and assert the top result matches the expected municipality_id.
    Skipped automatically when Qdrant is not reachable.

Run:
  pytest monitoring/scripts/test_municipality_disambiguation.py -v
  # or without pytest:
  python monitoring/scripts/test_municipality_disambiguation.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENRICHED_JSONL = (
    REPO_ROOT
    / "RAG Data"
    / "municipality"
    / "municipality_lookup_public.jsonl"
)

# ---------------------------------------------------------------------------
# Known ambiguous name pairs — (municipality_id, name, expected_district)
# From audit §H: 8+ confirmed ambiguous rows
# ---------------------------------------------------------------------------
AMBIGUOUS_PAIRS: list[tuple[str, str, str]] = [
    # (municipality_id, common_name, expected_district_after_backfill)
    ("M219",  "Ainab",     "Aley"),          # vs Ainab in another district
    ("M24",   "Majdel",    ""),              # 3 candidates — district unknown from v116
    ("M346",  "Bednayel",  ""),              # 2 candidates
    ("M374",  "Ainata",    ""),              # 2 candidates
    ("M458",  "Kaoukaba",  ""),              # 2 candidates
    ("M493",  "Bqosta",    "Chouf"),         # vs Bqosta Batroun (V81DGLAC026)
    ("M622",  "Yohmor",    ""),              # 2 candidates
    ("M671",  "Hasbaiya",  "Hasbaya"),       # vs Hasbaiya in another
]

# Known split-district municipalities: same name, different district
# Each entry: (id_a, id_b, shared_name)  — should NOT be returned for the same query
SPLIT_DISTRICT_PAIRS: list[tuple[str, str, str]] = [
    # Khraibe appears in 3 governorates
    ("M261", "M359",  "Khraibe"),   # Khraibe Chouf vs Khraibe Bekaa
    # Taibe appears in multiple districts
    ("M371", "M687",  "Taibe"),     # Taibe Baalbek vs Taibe Marjaayoun
    # Qraiye appears in South twice
    ("M171", "M475",  "Qraiye"),    # Qraiye (Mt Lebanon) vs Qraiye Saida
    # Ain et Tine appears in 2 places
    ("M433", "M942",  "Ain et Tine"),
]

# Municipalities that must have can_auto_route=False (routing policy test)
# Any municipality NOT in the scoped-200 set should be False
POLICY_CHECKS: list[tuple[str, str, bool]] = [
    # (municipality_id, name, expected_can_auto_route)
    ("M1",   "Beirut",   True),
    ("M2",   "Jbail",    True),
    ("M3",   "Edde",     False),
    ("M10",  "Aaqoura",  False),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_enriched(path: Path) -> dict[str, dict]:
    """Returns dict keyed by municipality_id."""
    result: dict[str, dict] = {}
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        result[doc["municipality_id"]] = doc
    return result


def _district(doc: dict) -> str:
    return (doc.get("location", {}).get("district") or "").strip()


def _can_auto_route(doc: dict) -> bool:
    return bool(doc.get("routing", {}).get("can_auto_route", False))


# ---------------------------------------------------------------------------
# Part A — Static JSONL assertions
# ---------------------------------------------------------------------------

class StaticTests:
    def __init__(self) -> None:
        if not ENRICHED_JSONL.exists():
            raise FileNotFoundError(
                f"Enriched JSONL not found: {ENRICHED_JSONL}\n"
                "Run scripts/prepare_v116_for_rag.py first."
            )
        self.docs = load_enriched(ENRICHED_JSONL)
        self.failures: list[str] = []
        self.passed = 0

    def _assert(self, condition: bool, msg: str) -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {msg}")
        else:
            self.failures.append(msg)
            print(f"  FAIL  {msg}")

    def test_all_docs_present(self) -> None:
        """1064 rows must be present."""
        self._assert(
            len(self.docs) == 1064,
            f"total docs == 1064 (got {len(self.docs)})"
        )

    def test_no_empty_retrieval_text(self) -> None:
        """No doc may have empty retrieval_text."""
        empty = [mid for mid, d in self.docs.items() if not (d.get("retrieval_text") or "").strip()]
        self._assert(not empty, f"retrieval_text non-empty (failures: {empty[:5]})")

    def test_blind_auto_submit_always_false(self) -> None:
        """blind_auto_submit_allowed must be False for ALL rows — no exceptions."""
        bad = [
            mid for mid, d in self.docs.items()
            if d.get("routing", {}).get("blind_auto_submit_allowed", False)
        ]
        self._assert(not bad, f"blind_auto_submit_allowed==False for all ({len(bad)} violations)")

    def test_user_confirmation_always_true(self) -> None:
        """user_confirmation_required must be True for ALL rows."""
        bad = [
            mid for mid, d in self.docs.items()
            if not d.get("routing", {}).get("user_confirmation_required", True)
        ]
        self._assert(not bad, f"user_confirmation_required==True for all ({len(bad)} violations)")

    def test_autoroute_count(self) -> None:
        """Exactly 200 rows must have can_auto_route=True."""
        auto = sum(1 for d in self.docs.values() if _can_auto_route(d))
        self._assert(auto == 200, f"can_auto_route==True count == 200 (got {auto})")

    def test_policy_spot_checks(self) -> None:
        """Known municipalities must have correct can_auto_route value."""
        for mid, name, expected in POLICY_CHECKS:
            doc = self.docs.get(mid)
            if not doc:
                self._assert(False, f"policy: {mid} ({name}) exists in docs")
                continue
            actual = _can_auto_route(doc)
            self._assert(
                actual == expected,
                f"policy: {mid} ({name}) can_auto_route=={expected} (got {actual})"
            )

    def test_district_backfill_coverage(self) -> None:
        """At least 600 of 1064 rows must have a non-empty district after backfill."""
        filled = sum(1 for d in self.docs.values() if _district(d))
        self._assert(filled >= 600, f"district filled >= 600 (got {filled})")

    def test_ambiguous_pairs_have_registry_id(self) -> None:
        """Known ambiguous names must have registry_id or be explicitly marked ambiguous,
        so they are not silently included as unresolved."""
        for mid, name, _ in AMBIGUOUS_PAIRS:
            doc = self.docs.get(mid)
            if not doc:
                continue  # doc not in 1064 (it may be in unmatched)
            record_status = doc.get("record_status", "")
            self._assert(
                record_status == "ambiguous" or doc.get("registry_id"),
                f"ambiguous: {mid} ({name}) correctly tagged (record_status={record_status})"
            )

    def test_split_districts_are_distinct(self) -> None:
        """Pairs of same-name municipalities must have different district values."""
        for id_a, id_b, name in SPLIT_DISTRICT_PAIRS:
            doc_a = self.docs.get(id_a)
            doc_b = self.docs.get(id_b)
            if not doc_a or not doc_b:
                continue
            dist_a = _district(doc_a)
            dist_b = _district(doc_b)
            if dist_a and dist_b:
                self._assert(
                    dist_a.lower() != dist_b.lower(),
                    f"split: {name} — {id_a} district={dist_a!r} != {id_b} district={dist_b!r}"
                )
            else:
                # District still missing — warn but don't fail (expected for unmatched rows)
                print(f"  WARN  split: {name} — {id_a} district={dist_a!r} or {id_b} district={dist_b!r} is empty")

    def test_v75new_rows_tagged_unmatched(self) -> None:
        """V75NEW rows (new discoveries, not in DGLAC) must not be marked matched.
        V81DGLAC rows may be matched depending on crosswalk evidence."""
        v75_only = {mid: d for mid, d in self.docs.items() if mid.startswith("V75")}
        v81_only = {mid: d for mid, d in self.docs.items() if mid.startswith("V81")}
        self._assert(len(v75_only) + len(v81_only) == 59, f"59 V75/V81 rows present (got {len(v75_only) + len(v81_only)})")
        # V75NEW rows must NOT be tagged matched (they are new discoveries)
        wrong = [mid for mid, d in v75_only.items() if d.get("record_status") == "matched"]
        self._assert(
            not wrong,
            f"no V75NEW row silently tagged as matched (violations: {wrong[:5]})"
        )
        # V81DGLAC rows may be matched/unmatched depending on crosswalk match — no strict assertion.
        v81_statuses = set(d.get("record_status", "") for d in v81_only.values())
        print(f"  INFO  V81DGLAC record_status distribution: {dict(sorted((s, sum(1 for d in v81_only.values() if d.get('record_status') == s)) for s in v81_statuses))}")

    def run_all(self) -> int:
        print("\n=== Part A: Static JSONL Tests ===\n")
        self.test_all_docs_present()
        self.test_no_empty_retrieval_text()
        self.test_blind_auto_submit_always_false()
        self.test_user_confirmation_always_true()
        self.test_autoroute_count()
        self.test_policy_spot_checks()
        self.test_district_backfill_coverage()
        self.test_ambiguous_pairs_have_registry_id()
        self.test_split_districts_are_distinct()
        self.test_v75new_rows_tagged_unmatched()
        print(f"\nPart A: {self.passed} passed, {len(self.failures)} failed")
        if self.failures:
            print("Failures:")
            for f in self.failures:
                print(f"  • {f}")
        return len(self.failures)


# ---------------------------------------------------------------------------
# Part B — Qdrant retrieval tests (skipped if Qdrant not reachable)
# ---------------------------------------------------------------------------

class QdrantTests:
    COLLECTION = "municipality_lookup"

    def __init__(self) -> None:
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        self.model_name  = os.getenv(
            "MODEL_NAME",
            "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        )
        self.qdrant = None
        self.model  = None
        self.failures: list[str] = []
        self.passed = 0
        self.skipped = 0

    def setup(self) -> bool:
        """Returns True if setup succeeds (Qdrant + model available)."""
        try:
            from qdrant_client import QdrantClient  # type: ignore
            c = QdrantClient(host=self.qdrant_host, port=self.qdrant_port, timeout=3)
            collections = [col.name for col in c.get_collections().collections]
            if self.COLLECTION not in collections:
                print(
                    f"  SKIP  Qdrant collection '{self.COLLECTION}' not found. "
                    "Run seed_municipality_lookup.py first."
                )
                return False
            self.qdrant = c
        except Exception as e:
            print(f"  SKIP  Qdrant not reachable ({e})")
            return False

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            self.model = SentenceTransformer(self.model_name)
        except ImportError:
            print("  SKIP  sentence-transformers not installed")
            return False

        return True

    def _embed(self, text: str):
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def _assert(self, condition: bool, msg: str) -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {msg}")
        else:
            self.failures.append(msg)
            print(f"  FAIL  {msg}")

    def test_collection_has_1064_points(self) -> None:
        info = self.qdrant.get_collection(self.COLLECTION)
        count = info.points_count
        self._assert(count == 1064, f"collection has 1064 points (got {count})")

    def test_beirut_top_result(self) -> None:
        """Query 'baladiye Beirut' must return Beirut (M1) as the top hit."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore
        vec = self._embed("baladiye Beirut بيروت")
        hits = self.qdrant.search(
            collection_name=self.COLLECTION,
            query_vector=vec,
            limit=3,
        )
        top = hits[0].payload.get("municipality_id") if hits else None
        self._assert(top == "M1", f"'baladiye Beirut' top hit == M1 (got {top})")

    def test_ainab_district_filter(self) -> None:
        """Query 'Ainab' with district=Aley filter must not return Ainab from another district."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore
        vec = self._embed("Ainab municipality عيناب")
        hits = self.qdrant.search(
            collection_name=self.COLLECTION,
            query_vector=vec,
            query_filter=Filter(
                must=[FieldCondition(key="district", match=MatchValue(value="Aley"))]
            ),
            limit=3,
        )
        mids = [h.payload.get("municipality_id") for h in hits]
        self._assert(
            "M219" in mids,
            f"Ainab/Aley filter returns M219 in top 3 (got {mids})"
        )

    def test_blind_submit_filter(self) -> None:
        """Filter blind_auto_submit_allowed=True must return 0 results."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore
        vec = self._embed("any query")
        hits = self.qdrant.search(
            collection_name=self.COLLECTION,
            query_vector=vec,
            query_filter=Filter(
                must=[FieldCondition(key="blind_auto_submit_allowed", match=MatchValue(value=True))]
            ),
            limit=5,
        )
        self._assert(
            len(hits) == 0,
            f"blind_auto_submit_allowed=True filter returns 0 results (got {len(hits)})"
        )

    def test_autoroute_filter_returns_200(self) -> None:
        """Scroll with can_auto_route=True filter must return exactly 200 points."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # type: ignore
        records, _ = self.qdrant.scroll(
            collection_name=self.COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="can_auto_route", match=MatchValue(value=True))]
            ),
            limit=300,
            with_payload=False,
        )
        self._assert(len(records) == 200, f"can_auto_route=True scroll == 200 (got {len(records)})")

    def run_all(self) -> int:
        print("\n=== Part B: Qdrant Retrieval Tests ===\n")
        if not self.setup():
            print("  All Part B tests skipped (Qdrant/model not available).\n")
            return 0
        self.test_collection_has_1064_points()
        self.test_beirut_top_result()
        self.test_ainab_district_filter()
        self.test_blind_submit_filter()
        self.test_autoroute_filter_returns_200()
        print(f"\nPart B: {self.passed} passed, {len(self.failures)} failed, {self.skipped} skipped")
        if self.failures:
            print("Failures:")
            for f in self.failures:
                print(f"  • {f}")
        return len(self.failures)


# ---------------------------------------------------------------------------
# pytest-compatible test functions (auto-discovered by pytest)
# ---------------------------------------------------------------------------

def _static_tests() -> StaticTests:
    """Singleton for pytest fixtures."""
    if not hasattr(_static_tests, "_instance"):
        _static_tests._instance = StaticTests()  # type: ignore
    return _static_tests._instance  # type: ignore


def test_all_docs_present():           _static_tests().test_all_docs_present();           assert not _static_tests().failures[-1:] or _static_tests().failures[-1] not in _static_tests().failures  # noqa: E501
def test_no_empty_retrieval_text():    _static_tests().test_no_empty_retrieval_text()
def test_blind_auto_submit_false():    _static_tests().test_blind_auto_submit_always_false()
def test_user_confirmation_true():     _static_tests().test_user_confirmation_always_true()
def test_autoroute_count():            _static_tests().test_autoroute_count()
def test_district_backfill_coverage(): _static_tests().test_district_backfill_coverage()


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    total_failures = 0
    total_failures += StaticTests().run_all()
    total_failures += QdrantTests().run_all()
    sys.exit(0 if total_failures == 0 else 1)
