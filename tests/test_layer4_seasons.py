"""Layer 4 — season classification + multiplier matrix tests.

Covers:
    - Gauss-Easter against known reference dates (2024–2030)
    - Holy Week is the 7 days ending the day before Easter
    - Each season window covers the spec'd date ranges
    - Holy Week overrides the surrounding season
    - Spec multipliers exact: LOW 1.20, MID 1.00, HIGH 0.85, PEAK 0.75
    - season_multiplier() returns the same value as the matrix

Runnable directly:
    python tests/test_layer4_seasons.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.lodging import (
    Season,
    SEASON_MULTIPLIERS,
    classify_season,
    gauss_easter,
    holy_week,
    season_multiplier,
)


# ---------- Easter / Holy Week ----------

def test_easter_2024_through_2030():
    """Reference Western Easter dates."""
    expected = {
        2024: date(2024, 3, 31),
        2025: date(2025, 4, 20),
        2026: date(2026, 4, 5),
        2027: date(2027, 3, 28),
        2028: date(2028, 4, 16),
        2029: date(2029, 4, 1),
        2030: date(2030, 4, 21),
    }
    for year, expected_date in expected.items():
        assert gauss_easter(year) == expected_date, \
            f"Easter {year} wrong: got {gauss_easter(year)}"


def test_holy_week_is_7_days_ending_day_before_easter():
    easter = gauss_easter(2026)
    start, end = holy_week(2026)
    assert end == easter - timedelta(days=1)
    assert (end - start).days == 6
    assert start == date(2026, 3, 29)
    assert end == date(2026, 4, 4)


def test_holy_week_overrides_mid_season():
    # 2026 Holy Week (Mar 29 – Apr 4) falls inside MID season.
    for d in (date(2026, 3, 29), date(2026, 4, 1), date(2026, 4, 4)):
        assert classify_season(d) is Season.PEAK, f"{d} should be PEAK"
    # Days flanking Holy Week revert to MID.
    assert classify_season(date(2026, 3, 28)) is Season.MID
    assert classify_season(date(2026, 4, 5)) is Season.MID  # Easter Sunday → MID


# ---------- season window coverage ----------

def test_peak_dec_15_through_jan_15():
    assert classify_season(date(2026, 12, 15)) is Season.PEAK
    assert classify_season(date(2026, 12, 31)) is Season.PEAK
    assert classify_season(date(2026, 1, 1)) is Season.PEAK
    assert classify_season(date(2026, 1, 15)) is Season.PEAK
    # Boundaries flip on the next day.
    assert classify_season(date(2026, 12, 14)) is Season.LOW
    assert classify_season(date(2026, 1, 16)) is Season.MID


def test_mid_jan_16_through_apr_14():
    for d in (date(2026, 1, 16), date(2026, 2, 1), date(2026, 3, 1)):
        assert classify_season(d) is Season.MID
    # Avoid Holy Week range when testing Apr 14.
    # Holy Week 2027 = Mar 21..26 — so Apr 14 2026 should be MID.
    assert classify_season(date(2026, 4, 14)) is Season.MID
    assert classify_season(date(2026, 4, 15)) is Season.LOW


def test_low_apr_15_through_may_31():
    for d in (date(2026, 4, 15), date(2026, 5, 1), date(2026, 5, 31)):
        assert classify_season(d) is Season.LOW
    assert classify_season(date(2026, 6, 1)) is Season.HIGH


def test_high_jun_through_aug():
    for d in (date(2026, 6, 1), date(2026, 7, 15), date(2026, 8, 31)):
        assert classify_season(d) is Season.HIGH
    assert classify_season(date(2026, 9, 1)) is Season.LOW


def test_low_sep_through_dec_14():
    for d in (date(2026, 9, 1), date(2026, 10, 15), date(2026, 11, 30),
              date(2026, 12, 14)):
        assert classify_season(d) is Season.LOW


# ---------- multiplier matrix ----------

def test_multiplier_matrix_exact_per_spec():
    assert SEASON_MULTIPLIERS[Season.LOW] == 1.20
    assert SEASON_MULTIPLIERS[Season.MID] == 1.00
    assert SEASON_MULTIPLIERS[Season.HIGH] == 0.85
    assert SEASON_MULTIPLIERS[Season.PEAK] == 0.75


def test_season_multiplier_matches_classification():
    # Sample one date per season window.
    samples = {
        Season.PEAK: date(2026, 12, 20),
        Season.MID: date(2026, 2, 14),
        Season.LOW: date(2026, 4, 25),
        Season.HIGH: date(2026, 7, 4),
    }
    for season, d in samples.items():
        assert classify_season(d) is season
        assert season_multiplier(d) == SEASON_MULTIPLIERS[season]


def test_holy_week_multiplier_is_peak():
    # Holy Week date in 2026.
    assert season_multiplier(date(2026, 4, 1)) == SEASON_MULTIPLIERS[Season.PEAK]


# ---------- runner ----------

def _all_tests():
    return [(n, o) for n, o in globals().items()
            if n.startswith("test_") and callable(o)]


def main():
    passed = failed = 0
    for name, fn in _all_tests():
        try:
            fn()
            passed += 1
            print(f"  ok   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\nLayer 4 seasons: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
