import csv
import json
import math
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
CLUSTERS_PATH = ROOT / "data" / "corpus" / "cedarfix_clusters_v1.csv"
PAIRS_PATH = ROOT / "data" / "corpus" / "cedarfix_pairs_v1.csv"
GPS_BOUNDS_PATH = ROOT / "data" / "knowledge_base" / "gps_bounds.json"

REQUIRED_REPORT_COLUMNS = {
    "report_id",
    "cluster_id",
    "language",
    "raw_text",
    "normalized_text",
    "normalization_applied",
    "district_code",
    "lat",
    "lon",
    "sector",
    "issue_type",
    "severity",
    "route_entity",
    "priority_label",
    "priority_reason",
    "hitl_required",
    "public_safety",
    "image_label",
    "image_consistent",
    "duplicate_role",
    "hard_negative_for_cluster_id",
    "created_at_offset_minutes",
    "labeler_id",
    "reviewer_id",
    "review_status",
    "notes",
}

REQUIRED_CLUSTER_COLUMNS = {
    "cluster_id",
    "sector",
    "issue_type",
    "district_code",
    "severity",
    "route_entity",
    "hitl_required",
    "public_safety",
    "report_count",
    "centroid_lat",
    "centroid_lon",
    "created_at_reference",
    "cluster_description",
    "canonical_report_id",
    "notes",
}

REQUIRED_PAIR_COLUMNS = {
    "pair_id",
    "report_id_a",
    "report_id_b",
    "pair_label",
    "cluster_id",
    "rationale",
}

VALID_LANGUAGES = {"ar", "arabizi", "en", "fr", "mixed"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_DUPLICATE_ROLES = {"ORIGINAL", "DUPLICATE", "RELATED", "NOISE"}
VALID_REVIEW_STATUSES = {"PENDING_SECOND_REVIEW", "APPROVED", "NEEDS_FIX"}
VALID_PAIR_LABELS = {"DUPLICATE", "RELATED", "HARD_NEGATIVE", "UNRELATED"}
VALID_IMAGE_LABELS = {"NONE", "POTHOLE", "FLOODING", "EXPOSED_WIRE", "GARBAGE", "STRUCTURAL_DAMAGE", "OTHER_INFRA"}
PAIR_ID_RE = re.compile(r"^PAIR-(B\d{3})-\d{4}$")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mean_lat = math.radians((lat1 + lat2) / 2)
    dlat = (lat1 - lat2) * 111_000
    dlon = (lon1 - lon2) * 111_000 * math.cos(mean_lat)
    return math.sqrt(dlat * dlat + dlon * dlon)


def add_error(errors: list[str], code: str, message: str) -> None:
    errors.append(f"{code}: {message}")


def validate() -> int:
    reports = read_csv(REPORTS_PATH)
    clusters = read_csv(CLUSTERS_PATH)
    pairs = read_csv(PAIRS_PATH) if PAIRS_PATH.exists() else []
    errors: list[str] = []
    warnings: list[str] = []

    if not reports:
        add_error(errors, "EMPTY_REPORTS", f"No rows in {REPORTS_PATH}")
        return finish(errors, warnings)

    if not clusters:
        add_error(errors, "EMPTY_CLUSTERS", f"No rows in {CLUSTERS_PATH}")
        return finish(errors, warnings)

    report_cols = set(reports[0].keys())
    cluster_cols = set(clusters[0].keys())
    pair_cols = set(pairs[0].keys()) if pairs else set()
    missing_report_cols = REQUIRED_REPORT_COLUMNS - report_cols
    missing_cluster_cols = REQUIRED_CLUSTER_COLUMNS - cluster_cols
    missing_pair_cols = REQUIRED_PAIR_COLUMNS - pair_cols if pairs else REQUIRED_PAIR_COLUMNS
    if missing_report_cols:
        add_error(errors, "REPORT_COLUMNS", f"Missing report columns: {sorted(missing_report_cols)}")
    if missing_cluster_cols:
        add_error(errors, "CLUSTER_COLUMNS", f"Missing cluster columns: {sorted(missing_cluster_cols)}")
    if missing_pair_cols:
        add_error(errors, "PAIR_COLUMNS", f"Missing pair columns or file: {sorted(missing_pair_cols)}")

    with GPS_BOUNDS_PATH.open("r", encoding="utf-8") as handle:
        bounds = json.load(handle)["lebanon"]

    cluster_by_id = {row["cluster_id"]: row for row in clusters}
    reports_by_id = {row["report_id"]: row for row in reports}

    if len(reports_by_id) != len(reports):
        add_error(errors, "DUPLICATE_REPORT_ID", "report_id values must be unique")
    if len(cluster_by_id) != len(clusters):
        add_error(errors, "DUPLICATE_CLUSTER_ID", "cluster_id values must be unique")
    if pairs and len({row["pair_id"] for row in pairs}) != len(pairs):
        add_error(errors, "DUPLICATE_PAIR_ID", "pair_id values must be unique")

    reports_by_cluster: dict[str, list[dict[str, str]]] = {}

    for row in reports:
        report_id = row["report_id"]
        cluster_id = row["cluster_id"]
        role = row["duplicate_role"]
        language = row["language"]
        severity = row["severity"]
        public_safety = row["public_safety"].lower() == "true"
        hitl_required = row["hitl_required"].lower() == "true"

        if language not in VALID_LANGUAGES:
            add_error(errors, "LANGUAGE", f"{report_id} has invalid language={language}")
        if severity not in VALID_SEVERITIES:
            add_error(errors, "SEVERITY", f"{report_id} has invalid severity={severity}")
        if role not in VALID_DUPLICATE_ROLES:
            add_error(errors, "DUPLICATE_ROLE", f"{report_id} has invalid duplicate_role={role}")
        if row["review_status"] not in VALID_REVIEW_STATUSES:
            add_error(errors, "REVIEW_STATUS", f"{report_id} has invalid review_status={row['review_status']}")
        reviewer_id = row.get("reviewer_id", "").strip()
        if row["review_status"] == "APPROVED" and (not reviewer_id or reviewer_id == "UNASSIGNED"):
            add_error(errors, "APPROVED_WITHOUT_REVIEWER", f"{report_id} status=APPROVED but reviewer_id=UNASSIGNED; second review required")
        if row["priority_label"] not in {"1", "2", "3", "4", "5"}:
            add_error(errors, "PRIORITY_LABEL", f"{report_id} has invalid priority_label={row['priority_label']}")

        if row["normalized_text"].strip() in {"", "SAME"}:
            add_error(errors, "NORMALIZED_TEXT", f"{report_id} has unusable normalized_text")
        expected_norm = "true" if language == "arabizi" else "false"
        if row["normalization_applied"].lower() != expected_norm:
            add_error(
                errors,
                "NORMALIZATION_FLAG",
                f"{report_id} has normalization_applied={row['normalization_applied']} expected {expected_norm}",
            )

        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except ValueError:
            add_error(errors, "GPS_PARSE", f"{report_id} has invalid lat/lon")
            continue

        if not (bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lon_min"] <= lon <= bounds["lon_max"]):
            add_error(errors, "GPS_BOUNDS", f"{report_id} is outside Lebanon bounds")

        if role == "NOISE":
            if cluster_id:
                add_error(errors, "NOISE_CLUSTER", f"{report_id} is NOISE but has cluster_id={cluster_id}")
            if not row["hard_negative_for_cluster_id"]:
                add_error(errors, "NOISE_TARGET", f"{report_id} is NOISE without hard_negative_for_cluster_id")
            elif row["hard_negative_for_cluster_id"] not in cluster_by_id:
                add_error(errors, "NOISE_TARGET", f"{report_id} targets unknown cluster {row['hard_negative_for_cluster_id']}")
        else:
            if not cluster_id:
                add_error(errors, "MISSING_CLUSTER", f"{report_id} role={role} requires cluster_id")
            elif cluster_id not in cluster_by_id:
                add_error(errors, "UNKNOWN_CLUSTER", f"{report_id} references unknown cluster {cluster_id}")
            else:
                reports_by_cluster.setdefault(cluster_id, []).append(row)
            if row["hard_negative_for_cluster_id"]:
                add_error(errors, "NON_NOISE_TARGET", f"{report_id} is not NOISE but has hard_negative_for_cluster_id")

        if row["sector"] in {"ELECTRICITY", "SAFETY"} and not hitl_required:
            add_error(errors, "HITL_POLICY", f"{report_id} sector={row['sector']} must be HITL")
        if severity == "CRITICAL" and public_safety and not hitl_required:
            add_error(errors, "HITL_POLICY", f"{report_id} critical public-safety report must be HITL")

        img_label = row.get("image_label", "")
        img_consistent = row.get("image_consistent", "")
        if img_label not in VALID_IMAGE_LABELS:
            add_error(errors, "IMAGE_LABEL", f"{report_id} has invalid image_label={img_label!r}")
        if img_consistent.lower() not in {"true", "false", "n/a"}:
            add_error(errors, "IMAGE_CONSISTENT", f"{report_id} has invalid image_consistent={img_consistent!r}")
        elif img_label == "NONE" and img_consistent.lower() != "n/a":
            add_error(errors, "IMAGE_CONSISTENT", f"{report_id} image_label=NONE requires image_consistent=N/A")
        elif img_label != "NONE" and img_consistent.lower() == "n/a":
            warnings.append(f"IMAGE_CONSISTENT: {report_id} has image_label={img_label} but image_consistent=N/A")

    for cluster in clusters:
        cluster_id = cluster["cluster_id"]
        cluster_reports = reports_by_cluster.get(cluster_id, [])
        if int(cluster["report_count"]) != len(cluster_reports):
            add_error(
                errors,
                "REPORT_COUNT",
                f"{cluster_id} report_count={cluster['report_count']} actual={len(cluster_reports)}",
            )

        canonical_id = cluster["canonical_report_id"]
        if canonical_id not in reports_by_id:
            add_error(errors, "CANONICAL_REPORT", f"{cluster_id} canonical report {canonical_id} missing")
        elif reports_by_id[canonical_id]["cluster_id"] != cluster_id:
            add_error(errors, "CANONICAL_REPORT", f"{cluster_id} canonical report belongs to another cluster")

        priority_values = {row["priority_label"] for row in cluster_reports}
        if len(priority_values) > 1:
            add_error(errors, "CLUSTER_PRIORITY", f"{cluster_id} has mixed priority labels {sorted(priority_values)}")

        if cluster["sector"] in {"ELECTRICITY", "SAFETY"} and cluster["hitl_required"].lower() != "true":
            add_error(errors, "CLUSTER_HITL", f"{cluster_id} sector={cluster['sector']} must be HITL")
        if cluster["severity"] == "CRITICAL" and cluster["public_safety"].lower() == "true":
            if cluster["hitl_required"].lower() != "true":
                add_error(errors, "CLUSTER_HITL", f"{cluster_id} critical public-safety cluster must be HITL")

        centroid_lat = float(cluster["centroid_lat"])
        centroid_lon = float(cluster["centroid_lon"])
        original_count = 0
        for row in cluster_reports:
            role = row["duplicate_role"]
            dist = distance_m(float(row["lat"]), float(row["lon"]), centroid_lat, centroid_lon)
            if role == "ORIGINAL":
                original_count += 1
                if dist > 1:
                    add_error(errors, "GPS_JITTER", f"{row['report_id']} ORIGINAL is {dist:.1f}m from centroid")
            elif role == "DUPLICATE" and not (30 <= dist <= 100):
                add_error(errors, "GPS_JITTER", f"{row['report_id']} DUPLICATE distance={dist:.1f}m outside 30-100m")
            elif role == "RELATED" and not (100 <= dist <= 300):
                add_error(errors, "GPS_JITTER", f"{row['report_id']} RELATED distance={dist:.1f}m outside 100-300m")

        if original_count != 1:
            add_error(errors, "ORIGINAL_COUNT", f"{cluster_id} has {original_count} ORIGINAL rows")

    seen_pair_keys: set[frozenset[str]] = set()
    paired_reports: set[str] = set()

    for pair in pairs:
        pair_id = pair["pair_id"]
        a = pair["report_id_a"]
        b = pair["report_id_b"]
        label = pair["pair_label"]
        cluster_id = pair["cluster_id"]

        if not PAIR_ID_RE.match(pair_id):
            add_error(errors, "PAIR_ID_FORMAT", f"{pair_id} must match PAIR-BNNN-NNNN")
        if a not in reports_by_id:
            add_error(errors, "PAIR_REPORT", f"{pair_id} report_id_a missing: {a}")
            continue
        if b not in reports_by_id:
            add_error(errors, "PAIR_REPORT", f"{pair_id} report_id_b missing: {b}")
            continue
        if a == b:
            add_error(errors, "PAIR_REPORT", f"{pair_id} pairs a report with itself")
        pair_key: frozenset[str] = frozenset({a, b})
        if pair_key in seen_pair_keys:
            add_error(errors, "PAIR_SYMMETRIC", f"{pair_id} is a symmetric duplicate of an earlier pair ({a} ↔ {b})")
        else:
            seen_pair_keys.add(pair_key)
        paired_reports.add(a)
        paired_reports.add(b)
        if label not in VALID_PAIR_LABELS:
            add_error(errors, "PAIR_LABEL", f"{pair_id} invalid pair_label={label}")
        if cluster_id and cluster_id not in cluster_by_id:
            add_error(errors, "PAIR_CLUSTER", f"{pair_id} unknown cluster_id={cluster_id}")

        report_a = reports_by_id[a]
        report_b = reports_by_id[b]
        if label == "DUPLICATE":
            if report_a["cluster_id"] != cluster_id or report_b["cluster_id"] != cluster_id:
                add_error(errors, "PAIR_DUPLICATE", f"{pair_id} duplicate pair must share cluster_id={cluster_id}")
            if "RELATED" in {report_a["duplicate_role"], report_b["duplicate_role"]}:
                add_error(errors, "PAIR_DUPLICATE", f"{pair_id} duplicate pair contains RELATED row")
        elif label == "RELATED":
            roles = {report_a["duplicate_role"], report_b["duplicate_role"]}
            if "RELATED" not in roles:
                add_error(errors, "PAIR_RELATED", f"{pair_id} related pair must include one RELATED row")
        elif label == "HARD_NEGATIVE":
            targets = {report_a["hard_negative_for_cluster_id"], report_b["hard_negative_for_cluster_id"]}
            if cluster_id not in targets:
                add_error(errors, "PAIR_HARD_NEGATIVE", f"{pair_id} hard negative must target cluster_id={cluster_id}")

    for row in reports:
        if row["duplicate_role"] != "NOISE" and row["report_id"] not in paired_reports:
            add_error(errors, "PAIR_COVERAGE", f"{row['report_id']} is not included in any pair")

    if pairs:
        # Per-batch negative ratio and subtype balance enforcement.
        # Minimum ratio by batch; any batch not listed defaults to the stricter B002+ threshold.
        BATCH_MIN_NEG_RATIO: dict[str, float] = {"B001": 0.20}
        DEFAULT_MIN_NEG_RATIO = 0.25  # B002 and beyond

        pairs_by_batch: dict[str, list[dict[str, str]]] = {}
        for pair in pairs:
            match = PAIR_ID_RE.match(pair["pair_id"])
            batch = match.group(1) if match else "UNKNOWN"
            pairs_by_batch.setdefault(batch, []).append(pair)

        for batch, batch_pairs in sorted(pairs_by_batch.items()):
            total = len(batch_pairs)
            negatives = [p for p in batch_pairs if p["pair_label"] in {"HARD_NEGATIVE", "UNRELATED"}]
            neg_count = len(negatives)
            ratio = neg_count / total if total else 0.0
            min_ratio = BATCH_MIN_NEG_RATIO.get(batch, DEFAULT_MIN_NEG_RATIO)
            if ratio < min_ratio:
                add_error(
                    errors,
                    "BATCH_NEG_RATIO",
                    f"Batch {batch}: {neg_count}/{total} ({ratio:.0%}) negative pairs; "
                    f"minimum is {min_ratio:.0%}",
                )
            # B002+ must also have ≥50% of negatives as UNRELATED (cross-cluster).
            # B001 is exempt because it was authored before this rule was formalised.
            if batch != "B001" and neg_count > 0:
                unrelated_count = sum(1 for p in negatives if p["pair_label"] == "UNRELATED")
                hard_negative_count = sum(1 for p in negatives if p["pair_label"] == "HARD_NEGATIVE")
                if hard_negative_count == 0:
                    add_error(
                        errors,
                        "BATCH_NEG_SUBTYPE",
                        f"Batch {batch}: no HARD_NEGATIVE pairs; each B002+ batch must include both "
                        f"HARD_NEGATIVE and UNRELATED negatives",
                    )
                if unrelated_count == 0:
                    add_error(
                        errors,
                        "BATCH_NEG_SUBTYPE",
                        f"Batch {batch}: no UNRELATED pairs; each B002+ batch must include both "
                        f"HARD_NEGATIVE and UNRELATED negatives",
                    )
                if unrelated_count < neg_count * 0.50:
                    add_error(
                        errors,
                        "BATCH_NEG_SUBTYPE",
                        f"Batch {batch}: {unrelated_count}/{neg_count} negatives are UNRELATED; "
                        f"≥50% must be UNRELATED (cross-cluster) for IEP-2 calibration",
                    )

    return finish(errors, warnings)


def finish(errors: list[str], warnings: list[str]) -> int:
    for warning in warnings:
        print(f"WARNING {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"FAILED: {len(errors)} errors, {len(warnings)} warnings")
        return 1
    print(f"OK: corpus validation passed with {len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
