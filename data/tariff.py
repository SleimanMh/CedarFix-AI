"""
SCE TOU-EV-9 (below 2kV) Tariff
Effective: 2024-10-01 | No End Date
Source: OpenEI USURDB, Southern California Edison Co, EIA ID 17609

Rate = Delivery + Generation (bundled)
Adjustments ($0.00115/kWh) included in all periods.

Period mapping (from OpenEI schedule grids):
  Period 1 -> Off-Peak:      $0.10986/kWh
  Period 2 -> Super Off-Peak:$0.19829/kWh  (mid-level off-peak)
  Period 3 -> Mid-Peak:      $0.38755/kWh
  Period 4 -> Super Off-Peak (summer): $0.18731/kWh
  Period 5 -> Mid-Peak (summer weekend): $0.34404/kWh
  Period 6 -> On-Peak (summer):$0.53025/kWh

Usage in optimizer:
  get_rate(hour, month, is_weekend) -> $/kWh
"""

# Energy rates by period index ($/kWh, inclusive of adjustments)
PERIOD_RATES = {
    1: 0.10986,  # Off-peak
    2: 0.19829,  # Mid / super off-peak
    3: 0.38755,  # On-peak (non-summer weekday)
    4: 0.18731,  # Super off-peak (summer)
    5: 0.34404,  # Mid-peak (summer weekend)
    6: 0.53025,  # On-peak (summer weekday)
}

# Summer months: June–September
SUMMER_MONTHS = {6, 7, 8, 9}

# Schedule grid: weekday_schedule[month][hour] -> period
# Derived from OpenEI schedule grid images
# Hours 0-23, months 1-12

def _build_weekday_schedule():
    """
    Non-summer (Jan-May, Oct-Dec):
      00-07: period 2
      08:    period 1  (transition)
      09-15: period 1
      16-20: period 3
      21-22: period 2
      23:    period 2

    Summer (Jun-Sep):
      00-07: period 4
      08-15: period 4
      16-20: period 6
      21-22: period 4
      23:    period 4
    """
    schedule = {}
    for month in range(1, 13):
        schedule[month] = {}
        is_summer = month in SUMMER_MONTHS
        for hour in range(24):
            if is_summer:
                if 16 <= hour <= 20:
                    schedule[month][hour] = 6   # On-peak
                else:
                    schedule[month][hour] = 4   # Super off-peak
            else:
                if hour <= 7:
                    schedule[month][hour] = 2   # Super off-peak
                elif 8 <= hour <= 15:
                    schedule[month][hour] = 1   # Off-peak
                elif 16 <= hour <= 20:
                    schedule[month][hour] = 3   # On-peak
                else:
                    schedule[month][hour] = 2   # Super off-peak
    return schedule


def _build_weekend_schedule():
    """
    Non-summer (Jan-May, Oct-Dec):
      00-07: period 2
      08-15: period 1
      16-20: period 3
      21-23: period 2

    Summer (Jun-Sep):
      00-07: period 4
      08-14: period 4
      15-18: period 5  (mid-peak weekend)
      19-20: period 4
      21-23: period 4
    """
    schedule = {}
    for month in range(1, 13):
        schedule[month] = {}
        is_summer = month in SUMMER_MONTHS
        for hour in range(24):
            if is_summer:
                if 15 <= hour <= 18:
                    schedule[month][hour] = 5   # Mid-peak
                else:
                    schedule[month][hour] = 4   # Super off-peak
            else:
                if hour <= 7:
                    schedule[month][hour] = 2
                elif 8 <= hour <= 15:
                    schedule[month][hour] = 1
                elif 16 <= hour <= 20:
                    schedule[month][hour] = 3
                else:
                    schedule[month][hour] = 2
    return schedule


WEEKDAY_SCHEDULE = _build_weekday_schedule()
WEEKEND_SCHEDULE = _build_weekend_schedule()


def get_rate(hour: int, month: int, is_weekend: bool) -> float:
    """
    Returns the energy rate in $/kWh for a given hour, month, and day type.

    Args:
        hour:       Hour of day (0-23)
        month:      Month (1-12)
        is_weekend: True for Saturday/Sunday

    Returns:
        Rate in $/kWh
    """
    if not (0 <= hour <= 23):
        raise ValueError(f"hour must be 0-23, got {hour}")
    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1-12, got {month}")

    schedule = WEEKEND_SCHEDULE if is_weekend else WEEKDAY_SCHEDULE
    period = schedule[month][hour]
    return PERIOD_RATES[period]


def get_daily_rate_profile(month: int, is_weekend: bool) -> list:
    """
    Returns a list of 24 rates ($/kWh) for each hour of a given day.
    Useful for feeding directly into the optimizer's cost vector.

    Args:
        month:      Month (1-12)
        is_weekend: True for Saturday/Sunday

    Returns:
        List of 24 floats, index = hour of day
    """
    return [get_rate(h, month, is_weekend) for h in range(24)]


def get_slot_rate_profile(month: int, is_weekend: bool, slots_per_hour: int = 4) -> list:
    """
    Returns a list of rates at sub-hourly resolution (e.g., 96 slots for 15-min intervals).
    Repeats each hourly rate for slots_per_hour slots.

    Args:
        month:          Month (1-12)
        is_weekend:     True for Saturday/Sunday
        slots_per_hour: Number of time slots per hour (default 4 = 15-min slots)

    Returns:
        List of 24 * slots_per_hour floats
    """
    hourly = get_daily_rate_profile(month, is_weekend)
    return [rate for rate in hourly for _ in range(slots_per_hour)]


if __name__ == "__main__":
    # Sanity check: print a full weekday profile for March and July
    print("=== Weekday Rate Profiles ===")
    for month, label in [(3, "March (non-summer)"), (7, "July (summer)")]:
        profile = get_daily_rate_profile(month, is_weekend=False)
        print(f"\n{label}:")
        for hour, rate in enumerate(profile):
            bar = "█" * int(rate * 20)
            print(f"  {hour:02d}:00  ${rate:.5f}  {bar}")

    print("\n=== 15-min Slot Profile Sample (July weekday, first 12 slots) ===")
    slots = get_slot_rate_profile(7, is_weekend=False)
    for i, r in enumerate(slots[:12]):
        print(f"  Slot {i:02d} ({i*15//60:02d}:{i*15%60:02d})  ${r:.5f}")
