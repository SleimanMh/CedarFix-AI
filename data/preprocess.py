"""
Data Preprocessing Pipeline
============================
Cleans and engineers features from raw ACN session data.

Input:  data/raw/acn_sessions_full_raw.csv
Output:
  data/processed/sessions_clean.parquet   — all cleaned sessions
  data/processed/train.parquet            — Mar 21 – Jul 31 2021
  data/processed/validation.parquet       — Aug 2021
  data/processed/holdout.parquet          — Sep 2021 (never touch until eval)
  data/processed/pipeline_report.json     — counts, drop reasons, split sizes

Run:
  pip install pandas numpy scikit-learn pyarrow
  python data/preprocess.py

Data quality decisions (documented explicitly for tradeoffs section):
  - 230 sessions with no userInputs: KEPT for optimizer (have kWh + times),
    EXCLUDED from forecast training (no kWhRequested feature available)
  - 864 sessions with no doneChargingTime: KEPT, flag added (done_charging_known)
  - No sessions dropped for missing disconnectTime (0 missing)
  - Sessions with duration <= 0: DROPPED (data corruption)
  - Sessions with kWhDelivered <= 0: DROPPED (no energy delivered, useless)
  - Sessions with avg_charge_rate > 20 kW: FLAGGED (above L2 max, likely data error)
    but KEPT — optimizer clips to 7.4 kW max anyway
"""

import ast
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW_PATH       = "data/raw/acn_sessions_full_raw.csv"
PROCESSED_DIR  = "data/processed"
REPORT_PATH    = os.path.join(PROCESSED_DIR, "pipeline_report.json")

# ── Split boundaries (UTC — data is stored as GMT) ───────────────────────────
TRAIN_START      = datetime(2021, 3, 21, tzinfo=timezone.utc)
TRAIN_END        = datetime(2021, 7, 31, 23, 59, 59, tzinfo=timezone.utc)
VALIDATION_START = datetime(2021, 8,  1, tzinfo=timezone.utc)
VALIDATION_END   = datetime(2021, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
HOLDOUT_START    = datetime(2021, 9,  1, tzinfo=timezone.utc)
HOLDOUT_END      = datetime(2021, 9, 14, 23, 59, 59, tzinfo=timezone.utc)

# ── Constants ─────────────────────────────────────────────────────────────────
DATETIME_FMT    = "%a, %d %b %Y %H:%M:%S GMT"
MAX_CHARGE_RATE = 20.0   # kW — flag above this (L2 EVSE max ~7.2 kW typical)
SLOT_MINUTES    = 15     # time resolution for demand aggregation


def parse_datetime(s) -> pd.Timestamp:
    """Parse ACN datetime string to UTC-aware Timestamp."""
    if pd.isna(s):          # handles float NaN, None, pd.NaT
        return pd.NaT
    s = str(s).strip()
    if not s:
        return pd.NaT
    try:
        dt = datetime.strptime(s, DATETIME_FMT)
        return pd.Timestamp(dt, tz="UTC")
    except ValueError:
        return pd.NaT


def parse_user_inputs(s: str) -> dict:
    """
    Extract kWhRequested, requestedDeparture, minutesAvailable from
    the nested userInputs JSON-like column.
    Returns dict with keys or NaN values if unparseable.
    """
    result = {
        "kwh_requested":        np.nan,
        "requested_departure":  pd.NaT,
        "minutes_available":    np.nan,
        "miles_requested":      np.nan,
        "wh_per_mile":          np.nan,
        "has_user_inputs":      False,
    }
    if pd.isna(s):          # handles float NaN, None
        return result
    if not str(s).strip():
        return result

    try:
        parsed = ast.literal_eval(s)
        if not parsed:
            return result
        ui = parsed[0]
        result["kwh_requested"]       = float(ui.get("kWhRequested", np.nan))
        result["minutes_available"]   = float(ui.get("minutesAvailable", np.nan))
        result["miles_requested"]     = float(ui.get("milesRequested", np.nan))
        result["wh_per_mile"]         = float(ui.get("WhPerMile", np.nan))
        result["has_user_inputs"]     = True

        dep_str = ui.get("requestedDeparture", "")
        if dep_str:
            result["requested_departure"] = parse_datetime(dep_str)
    except Exception:
        pass

    return result


def cyclic_encode(values: pd.Series, max_val: float):
    """Encode a cyclic feature (hour, day, month) as sin/cos pair."""
    sin = np.sin(2 * np.pi * values / max_val)
    cos = np.cos(2 * np.pi * values / max_val)
    return sin, cos


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer all time and session features."""

    # ── Time features from connectionTime ────────────────────────────────────
    df["hour"]          = df["connection_time"].dt.hour
    df["minute"]        = df["connection_time"].dt.minute
    df["day_of_week"]   = df["connection_time"].dt.dayofweek   # 0=Mon
    df["month"]         = df["connection_time"].dt.month
    df["day_of_year"]   = df["connection_time"].dt.dayofyear
    df["is_weekend"]    = (df["day_of_week"] >= 5).astype(int)
    df["is_summer"]     = df["month"].isin([6, 7, 8, 9]).astype(int)

    # Cyclic encodings — prevent model from thinking 23:00 is far from 0:00
    df["hour_sin"],    df["hour_cos"]    = cyclic_encode(df["hour"],        24)
    df["dow_sin"],     df["dow_cos"]     = cyclic_encode(df["day_of_week"],  7)
    df["month_sin"],   df["month_cos"]   = cyclic_encode(df["month"],       12)
    df["doy_sin"],     df["doy_cos"]     = cyclic_encode(df["day_of_year"], 365)

    # 15-min slot index within day (0–95)
    df["slot_of_day"] = df["hour"] * 4 + df["minute"] // 15

    # ── Session duration features ─────────────────────────────────────────────
    df["duration_hours"] = (
        (df["disconnect_time"] - df["connection_time"])
        .dt.total_seconds() / 3600
    )

    # Time until requested departure (hours) — key optimizer feature
    df["hours_until_departure"] = (
        (df["requested_departure"] - df["connection_time"])
        .dt.total_seconds() / 3600
    )

    # Average actual charge rate
    df["avg_charge_rate_kw"] = (
        df["kwh_delivered"] / df["duration_hours"]
    ).replace([np.inf, -np.inf], np.nan)

    # SOC proxy: fraction of requested energy delivered
    df["energy_fulfillment_ratio"] = (
        df["kwh_delivered"] / df["kwh_requested"]
    ).clip(0, 1.5)   # cap at 150% (overdelivery possible if user stayed longer)

    # Flag high charge rates (above L2 max — likely data error)
    df["high_rate_flag"] = (
        df["avg_charge_rate_kw"] > MAX_CHARGE_RATE
    ).astype(int)

    # Done charging known flag
    df["done_charging_known"] = (~df["done_charging_time"].isna()).astype(int)

    return df


def aggregate_demand(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-session data into a time series of concurrent load per
    15-minute slot. Used as the forecast target variable.

    For each 15-min slot, computes:
      - n_active:    number of EVs connected (plugged in)
      - n_charging:  number actively charging (proxy: connected + energy remaining)
      - total_kw:    sum of avg charge rates for active sessions
      - slot_start:  timestamp of slot start

    This is the demand forecast target: total_kw per slot.
    """
    # Build a 15-min slot time index over the full data range
    start = df["connection_time"].min().floor("15min")
    end   = df["disconnect_time"].max().ceil("15min")
    slots = pd.date_range(start=start, end=end, freq="15min", tz="UTC")

    records = []
    for slot_start in slots:
        slot_end = slot_start + pd.Timedelta(minutes=15)

        # Sessions active during this slot: connected before slot_end,
        # disconnected after slot_start
        active = df[
            (df["connection_time"] < slot_end) &
            (df["disconnect_time"] > slot_start)
        ]

        n_active   = len(active)
        total_kw   = active["avg_charge_rate_kw"].dropna().sum()
        kwh_active = active["kwh_delivered"].sum()

        records.append({
            "slot_start":   slot_start,
            "hour":         slot_start.hour,
            "minute":       slot_start.minute,
            "day_of_week":  slot_start.dayofweek,
            "month":        slot_start.month,
            "is_weekend":   int(slot_start.dayofweek >= 5),
            "is_summer":    int(slot_start.month in [6, 7, 8, 9]),
            "slot_of_day":  slot_start.hour * 4 + slot_start.minute // 15,
            "n_active":     n_active,
            "total_kw":     round(total_kw, 4),
            "kwh_in_slot":  round(kwh_active, 4),
        })

    demand_df = pd.DataFrame(records)

    # Add cyclic features to demand series too
    demand_df["hour_sin"],  demand_df["hour_cos"]  = cyclic_encode(demand_df["hour"],       24)
    demand_df["dow_sin"],   demand_df["dow_cos"]   = cyclic_encode(demand_df["day_of_week"],  7)
    demand_df["month_sin"], demand_df["month_cos"] = cyclic_encode(demand_df["month"],       12)

    # Lag features (previous 1h, 4h, 24h same slot)
    demand_df = demand_df.sort_values("slot_start").reset_index(drop=True)
    demand_df["lag_4"]   = demand_df["total_kw"].shift(4)    # 1 hour ago
    demand_df["lag_16"]  = demand_df["total_kw"].shift(16)   # 4 hours ago
    demand_df["lag_96"]  = demand_df["total_kw"].shift(96)   # 24 hours ago
    demand_df["lag_672"] = demand_df["total_kw"].shift(672)  # 1 week ago

    # Rolling stats (last 4 slots = 1 hour)
    demand_df["rolling_mean_1h"] = (
        demand_df["total_kw"].rolling(4, min_periods=1).mean()
    )
    demand_df["rolling_std_1h"] = (
        demand_df["total_kw"].rolling(4, min_periods=1).std().fillna(0)
    )

    return demand_df


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    report = {}

    print("=== ACN Data Preprocessing Pipeline ===\n")

    # ── 1. Load raw data ──────────────────────────────────────────────────────
    print(f"Loading {RAW_PATH} ...")
    raw = pd.read_csv(RAW_PATH)
    report["raw_rows"] = len(raw)
    print(f"  Raw rows: {len(raw)}")

    # ── 2. Parse datetimes ────────────────────────────────────────────────────
    print("Parsing datetimes ...")
    raw["connection_time"]    = raw["connectionTime"].apply(parse_datetime)
    raw["disconnect_time"]    = raw["disconnectTime"].apply(parse_datetime)
    raw["done_charging_time"] = raw["doneChargingTime"].apply(parse_datetime)

    # ── 3. Parse userInputs ───────────────────────────────────────────────────
    print("Parsing userInputs ...")
    ui_parsed = raw["userInputs"].apply(parse_user_inputs).apply(pd.Series)
    raw = pd.concat([raw, ui_parsed], axis=1)

    # ── 4. Rename and select columns ──────────────────────────────────────────
    df = raw.rename(columns={
        "_id":         "session_id_raw",
        "sessionID":   "session_id",
        "stationID":   "station_id",
        "spaceID":     "space_id",
        "siteID":      "site_id",
        "clusterID":   "cluster_id",
        "userID":      "user_id",
        "kWhDelivered":"kwh_delivered",
        "timezone":    "timezone",
    })[[
        "session_id", "station_id", "space_id", "site_id", "cluster_id",
        "user_id", "connection_time", "disconnect_time", "done_charging_time",
        "kwh_delivered", "kwh_requested", "requested_departure",
        "minutes_available", "miles_requested", "wh_per_mile",
        "has_user_inputs", "timezone"
    ]].copy()

    df["kwh_delivered"] = pd.to_numeric(df["kwh_delivered"], errors="coerce")

    # ── 5. Drop invalid rows ──────────────────────────────────────────────────
    print("Dropping invalid rows ...")
    n_before = len(df)

    # Drop if connection or disconnect time is missing
    df = df.dropna(subset=["connection_time", "disconnect_time"])
    report["dropped_missing_times"] = n_before - len(df)

    # Compute duration to check validity
    df["_duration"] = (
        df["disconnect_time"] - df["connection_time"]
    ).dt.total_seconds() / 3600

    # Drop if duration <= 0
    n_before = len(df)
    df = df[df["_duration"] > 0]
    report["dropped_zero_duration"] = n_before - len(df)

    # Drop if kWhDelivered <= 0 or missing
    n_before = len(df)
    df = df[df["kwh_delivered"].notna() & (df["kwh_delivered"] > 0)]
    report["dropped_zero_kwh"] = n_before - len(df)

    df = df.drop(columns=["_duration"])
    report["clean_rows"] = len(df)
    print(f"  Clean rows: {len(df)} "
          f"(dropped {report['raw_rows'] - len(df)} total)")

    # ── 6. Engineer features ──────────────────────────────────────────────────
    print("Engineering features ...")
    df = build_features(df)

    # ── 7. Save full clean dataset ────────────────────────────────────────────
    clean_path = os.path.join(PROCESSED_DIR, "sessions_clean.parquet")
    df.to_parquet(clean_path, index=False)
    print(f"  Saved: {clean_path}")

    # ── 8. Train/val/holdout split ────────────────────────────────────────────
    print("Splitting into train / validation / holdout ...")

    train = df[
        (df["connection_time"] >= TRAIN_START) &
        (df["connection_time"] <= TRAIN_END)
    ].copy()

    validation = df[
        (df["connection_time"] >= VALIDATION_START) &
        (df["connection_time"] <= VALIDATION_END)
    ].copy()

    holdout = df[
        (df["connection_time"] >= HOLDOUT_START) &
        (df["connection_time"] <= HOLDOUT_END)
    ].copy()

    train.to_parquet(os.path.join(PROCESSED_DIR, "train.parquet"), index=False)
    validation.to_parquet(os.path.join(PROCESSED_DIR, "validation.parquet"), index=False)
    holdout.to_parquet(os.path.join(PROCESSED_DIR, "holdout.parquet"), index=False)

    report["train_rows"]      = len(train)
    report["validation_rows"] = len(validation)
    report["holdout_rows"]    = len(holdout)

    print(f"  Train:      {len(train)} sessions "
          f"({TRAIN_START.date()} – {TRAIN_END.date()})")
    print(f"  Validation: {len(validation)} sessions "
          f"({VALIDATION_START.date()} – {VALIDATION_END.date()})")
    print(f"  Holdout:    {len(holdout)} sessions "
          f"({HOLDOUT_START.date()} – {HOLDOUT_END.date()})")

    # ── 9. Aggregate demand time series ───────────────────────────────────────
    print("Aggregating demand time series (15-min slots) ...")
    demand = aggregate_demand(df)
    demand_path = os.path.join(PROCESSED_DIR, "demand_timeseries.parquet")
    demand.to_parquet(demand_path, index=False)
    report["demand_slots"] = len(demand)
    print(f"  Demand slots: {len(demand)} "
          f"({demand['slot_start'].min()} – {demand['slot_start'].max()})")

    # Split demand series too
    demand_train = demand[
        (demand["slot_start"] >= TRAIN_START) &
        (demand["slot_start"] <= TRAIN_END)
    ]
    demand_val = demand[
        (demand["slot_start"] >= VALIDATION_START) &
        (demand["slot_start"] <= VALIDATION_END)
    ]
    demand_holdout = demand[
        (demand["slot_start"] >= HOLDOUT_START) &
        (demand["slot_start"] <= HOLDOUT_END)
    ]

    demand_train.to_parquet(
        os.path.join(PROCESSED_DIR, "demand_train.parquet"), index=False)
    demand_val.to_parquet(
        os.path.join(PROCESSED_DIR, "demand_validation.parquet"), index=False)
    demand_holdout.to_parquet(
        os.path.join(PROCESSED_DIR, "demand_holdout.parquet"), index=False)

    # ── 10. Save report ───────────────────────────────────────────────────────
    report["feature_columns"] = [
        c for c in df.columns
        if c not in ["session_id", "station_id", "space_id",
                     "site_id", "cluster_id", "user_id", "timezone"]
    ]
    report["forecast_features"] = [
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
        "month_sin", "month_cos", "is_weekend", "is_summer",
        "slot_of_day", "lag_4", "lag_16", "lag_96", "lag_672",
        "rolling_mean_1h", "rolling_std_1h"
    ]
    report["optimizer_required_fields"] = [
        "connection_time", "disconnect_time", "requested_departure",
        "kwh_delivered", "kwh_requested", "avg_charge_rate_kw",
        "hours_until_departure", "has_user_inputs"
    ]
    report["sessions_without_user_inputs"] = int(
        (~df["has_user_inputs"]).sum()
    )
    report["note_no_user_inputs"] = (
        "230 sessions have no userInputs (no kWhRequested or departure). "
        "Kept in optimizer dataset (have kWh + times). "
        "Excluded from forecast training (missing kwh_requested feature)."
    )

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n  Report saved: {REPORT_PATH}")
    print("\n=== Pipeline complete ===")
    print(f"  Clean sessions:  {report['clean_rows']}")
    print(f"  Demand slots:    {report['demand_slots']}")
    print(f"  Train / Val / Holdout: "
          f"{report['train_rows']} / "
          f"{report['validation_rows']} / "
          f"{report['holdout_rows']}")


if __name__ == "__main__":
    main()
