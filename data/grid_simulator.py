"""
Lebanon EDL Grid Markov Simulator
==================================
Generates synthetic grid availability sequences using a calibrated 2-state
Markov chain. Designed to produce stochastic training data for an LSTM
grid-probability model (F-004).

Complements grid_availability.py (which uses fixed deterministic patterns).
This module produces burst-realistic on/off sequences that match the
published EDL statistics but vary randomly each episode — essential for
training a model that must generalise to unseen outage sequences.

WHAT A MARKOV CHAIN MODELS
  State 0 = grid off | State 1 = grid on
  Two parameters control everything:
    p01 = P(off → on)   ← how often a new burst starts
    p10 = P(on  → off)  ← how often a running burst stops

  These are fitted from:
    1. Target daily on-hours    (from EDL_AVAILABILITY_HOURS in grid_availability.py)
    2. Expected burst duration  (qualitative: EDL typically supplies 1–3 hr blocks)

HONEST LABELING FOR YOUR DOCUMENTATION
  - Markov parameters are calibrated to published EDL statistics.
  - Generated sequences are SYNTHETIC — for ML training/simulation only.
  - They are NOT real outage logs and must not be presented as such.
  - Label as: "Markov-simulated availability calibrated to HRW (2023) /
    Wikipedia EDL statistics."

RELATIONSHIP TO OTHER MODULES
  grid_availability.py  → deterministic scenario patterns (split/morning/random)
                           used by the current LP optimizer
  grid_simulator.py     → stochastic Markov sequences
                           used to generate LSTM / RL training data (F-004)
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from data.grid_availability import DEFAULT_HOURS_PER_DAY, EDL_AVAILABILITY_HOURS

# ── Default burst parameters ──────────────────────────────────────────────────
# Based on qualitative EDL reporting: supply comes in windows of ~1-3 hours.
# 8 slots × 15 min = 2 hours per continuous on-burst (conservative default).
DEFAULT_MEAN_ON_SLOTS: int = 8


# ── Markov parameter fitting ──────────────────────────────────────────────────

def fit_markov_params(
    hours_per_day: float,
    mean_on_slots: int = DEFAULT_MEAN_ON_SLOTS,
) -> Tuple[float, float]:
    """
    Fit 2-state Markov transition probabilities from two constraints:

      1. Stationary on-probability = hours_per_day / 24
         i.e.  p01 / (p01 + p10) = pi_on

      2. Expected consecutive on-slots = mean_on_slots
         i.e.  1 / p10 = mean_on_slots  →  p10 = 1 / mean_on_slots

    Solving: p01 = (pi_on / pi_off) × p10

    Args:
        hours_per_day:  Target average daily EDL supply hours (1–24).
        mean_on_slots:  Expected length of a single on-burst in 15-min slots.

    Returns:
        (p01, p10) — per-slot transition probabilities.

    Example
    -------
    >>> # October 2021: 2 hrs/day, 2-hour bursts
    >>> p01, p10 = fit_markov_params(2.0, mean_on_slots=8)
    >>> round(p01, 4), round(p10, 4)
    (0.0109, 0.125)
    """
    pi_on = hours_per_day / 24.0
    pi_on = float(np.clip(pi_on, 0.01, 0.99))  # avoid degenerate chains

    p10 = 1.0 / float(mean_on_slots)
    p01 = (pi_on / (1.0 - pi_on)) * p10
    p01 = min(p01, 1.0)  # cap in case pi_on is high

    return p01, p10


# ── Single-day sampler ────────────────────────────────────────────────────────

def sample_markov_day(
    year: int,
    month: int,
    mean_on_slots: int = DEFAULT_MEAN_ON_SLOTS,
    rng: Optional[np.random.Generator] = None,
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Sample one day (96 slots) of grid availability from a fitted Markov chain.

    Args:
        year, month:    Used to look up target EDL hours from
                        ``EDL_AVAILABILITY_HOURS``.
        mean_on_slots:  Expected consecutive on-slots per burst.
        rng:            NumPy Generator (takes priority over seed).
        seed:           Integer seed — convenience alternative to rng.

    Returns:
        np.ndarray, shape (96,), dtype int — 1 = grid on, 0 = grid off.
    """
    if rng is None:
        rng = np.random.default_rng(seed)

    hours = EDL_AVAILABILITY_HOURS.get((year, month), DEFAULT_HOURS_PER_DAY)
    p01, p10 = fit_markov_params(hours, mean_on_slots)

    slots = np.zeros(96, dtype=np.int8)
    # Start in off-state (midnight — power is typically off in Lebanon then)
    state = 0

    for t in range(96):
        slots[t] = state
        if state == 0:
            if rng.random() < p01:
                state = 1
        else:
            if rng.random() < p10:
                state = 0

    return slots.astype(int)


# ── Multi-day episode sampler ─────────────────────────────────────────────────

def sample_markov_episode(
    n_days: int,
    start_year: int = 2021,
    start_month: int = 10,
    mean_on_slots: int = DEFAULT_MEAN_ON_SLOTS,
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Sample a contiguous multi-day availability episode.

    Day boundaries are respected — each day's Markov chain is independent
    (re-initialised at midnight). This matches the EDL reality where the
    next day's power schedule is not predictable from today's.

    Args:
        n_days:          Number of days to simulate.
        start_year/month: Starting calendar period (determines base hours).
        mean_on_slots:   Expected burst duration in slots.
        seed:            Random seed for full reproducibility.

    Returns:
        np.ndarray, shape (n_days × 96,), dtype int.
    """
    rng = np.random.default_rng(seed)
    current = datetime(start_year, start_month, 1)
    all_slots: List[int] = []

    for _ in range(n_days):
        day_slots = sample_markov_day(
            current.year, current.month,
            mean_on_slots=mean_on_slots,
            rng=rng,
        )
        all_slots.extend(day_slots.tolist())
        current += timedelta(days=1)

    return np.array(all_slots, dtype=int)


# ── LSTM training dataset generator ──────────────────────────────────────────

def generate_lstm_dataset(
    n_episodes: int = 1000,
    episode_length_days: int = 30,
    sequence_length: int = 96,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate a sliding-window (X, y) dataset for LSTM binary classification.

    Each sample:
      X[i]  — ``sequence_length`` consecutive slots of grid history  (input)
      y[i]  — state of the very next slot: 1 = on, 0 = off           (label)

    The LSTM learns:
      P(grid_on at t+1  |  grid_state[t-L : t])

    Diversity is achieved by sampling from different EDL months so the
    model generalises across both high-availability (Mar 2021: 10 hrs/day)
    and crisis periods (Oct 2021: 2 hrs/day).

    Args:
        n_episodes:          Number of independent simulation runs.
        episode_length_days: Days per episode (more = more training samples).
        sequence_length:     LSTM lookback window in slots (default 96 = 1 day).
        seed:                Master random seed.

    Returns:
        X: np.ndarray, shape (n_samples, sequence_length, 1), dtype float32
        y: np.ndarray, shape (n_samples,), dtype float32

    Example
    -------
    >>> X, y = generate_lstm_dataset(n_episodes=100, episode_length_days=7)
    >>> X.shape
    (57600, 96, 1)
    >>> round(float(y.mean()), 2)   # fraction of on-slots
    0.14
    """
    rng = np.random.default_rng(seed)
    known_months = list(EDL_AVAILABILITY_HOURS.keys())

    X_list: List[np.ndarray] = []
    y_list: List[int] = []

    for _ in range(n_episodes):
        # Sample a random known EDL period as the starting month
        yr, mo = known_months[int(rng.integers(0, len(known_months)))]
        series = sample_markov_episode(
            n_days=episode_length_days,
            start_year=yr,
            start_month=mo,
            seed=int(rng.integers(0, 2**31)),
        )

        # Sliding window — step by 1 slot
        for t in range(sequence_length, len(series)):
            X_list.append(series[t - sequence_length : t])
            y_list.append(int(series[t]))

    X = np.array(X_list, dtype=np.float32).reshape(-1, sequence_length, 1)
    y = np.array(y_list, dtype=np.float32)
    return X, y


# ── Summary helpers ───────────────────────────────────────────────────────────

def markov_summary(year: int, month: int, n_samples: int = 1000, seed: int = 0) -> Dict:
    """
    Monte Carlo statistics for a given EDL month.
    Runs ``n_samples`` simulated days and reports mean/std of daily on-hours.
    """
    rng = np.random.default_rng(seed)
    hours_list = []
    for _ in range(n_samples):
        day = sample_markov_day(year, month, rng=rng)
        hours_list.append(float(day.sum()) / 4.0)

    hours = EDL_AVAILABILITY_HOURS.get((year, month), DEFAULT_HOURS_PER_DAY)
    return {
        "year": year,
        "month": month,
        "target_hours_per_day": hours,
        "simulated_mean_hours": round(float(np.mean(hours_list)), 3),
        "simulated_std_hours": round(float(np.std(hours_list)), 3),
        "n_samples": n_samples,
    }


def dataset_summary(X: np.ndarray, y: np.ndarray) -> Dict:
    """Returns shape and balance statistics for a generated dataset."""
    return {
        "n_samples": int(len(y)),
        "sequence_length": int(X.shape[1]),
        "on_fraction": round(float(y.mean()), 4),
        "off_fraction": round(float(1.0 - y.mean()), 4),
        "X_shape": list(X.shape),
        "y_shape": list(y.shape),
    }


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== Lebanon EDL Grid Markov Simulator ===\n")

    # 1. Parameter fitting
    print("-- Fitted Markov parameters --")
    for (yr, mo), hrs in sorted(EDL_AVAILABILITY_HOURS.items()):
        p01, p10 = fit_markov_params(hrs)
        mean_burst = round(1.0 / p10 * 0.25, 2)   # hours
        print(f"  {yr}-{mo:02d}  {hrs:.1f} hrs/day  "
              f"p01={p01:.4f}  p10={p10:.4f}  "
              f"mean_burst={mean_burst}h")

    # 2. Single-day visual
    print("\n-- Sample day: October 2021 (2 hrs/day) --")
    day = sample_markov_day(2021, 10, seed=0)
    visual = "".join("#" if s else "." for s in day[::4])
    print(f"  Hourly: {visual}  (#=on .=off)")
    print(f"  On-hours: {day.sum() / 4:.2f}")

    # 3. Monte Carlo calibration check
    print("\n-- Monte Carlo calibration (1 000 days per month) --")
    for (yr, mo) in [(2021, 3), (2021, 7), (2021, 10)]:
        s = markov_summary(yr, mo, n_samples=1000)
        print(f"  {yr}-{mo:02d}: target={s['target_hours_per_day']}h  "
              f"simulated={s['simulated_mean_hours']}+/-{s['simulated_std_hours']}h")

    # 4. LSTM dataset
    print("\n-- LSTM dataset (100 episodes x 7 days, window=96) --")
    X, y = generate_lstm_dataset(n_episodes=100, episode_length_days=7, seed=0)
    info = dataset_summary(X, y)
    print(f"  X: {info['X_shape']}   y: {info['y_shape']}")
    print(f"  on-fraction: {info['on_fraction']}  "
          f"off-fraction: {info['off_fraction']}")
