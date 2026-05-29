"""Layer 5 — India scoring engine tests.

Covers:
    - score_price clamping and linearity
    - score_location at 0 / mid / 5+ km
    - score_season for each season + None
    - score_lodging_signal for each color + None
    - score_option weighting sums (price 0.40 + location 0.20 +
      season 0.15 + lodging 0.25 = 1.00)
    - Invalid inputs raise
    - Custom typical_table override

Runnable directly:
    python tests/test_layer5_india_scoring.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.india import (
    AccommodationCategory,
    SCORE_WEIGHTS,
    score_lodging_signal,
    score_location,
    score_option,
    score_price,
    score_season,
)
from intel.lodging.scoring import LodgingColor
from intel.lodging.seasons import Season


# ---------- weights are sane ----------

def test_weights_sum_to_one():
    assert round(sum(SCORE_WEIGHTS.values()), 4) == 1.0


def test_weights_documented_values():
    assert SCORE_WEIGHTS["price"] == 0.40
    assert SCORE_WEIGHTS["location"] == 0.20
    assert SCORE_WEIGHTS["season"] == 0.15
    assert SCORE_WEIGHTS["lodging_signal"] == 0.25


# ---------- score_price ----------

def test_price_at_or_below_70pct_is_100():
    assert score_price(10.0, AccommodationCategory.HOSTEL_DORM) == 100.0   # 10/15 ≈ 0.67
    assert score_price(5.0, AccommodationCategory.HOSTEL_DORM) == 100.0    # well under


def test_price_at_or_above_130pct_is_0():
    # HOSTEL_DORM typical = 15; 130% = 19.5
    assert score_price(19.5, AccommodationCategory.HOSTEL_DORM) == 0.0
    assert score_price(30.0, AccommodationCategory.HOSTEL_DORM) == 0.0


def test_price_linearity_at_typical_is_50():
    # At ratio 1.0 (typical), score = (1.30 - 1.00) / 0.60 * 100 = 50.0
    assert score_price(15.0, AccommodationCategory.HOSTEL_DORM) == 50.0
    assert score_price(35.0, AccommodationCategory.HOSTEL_PRIVATE_ROOM) == 50.0


def test_price_rejects_negative():
    try:
        score_price(-1, AccommodationCategory.HOSTEL_DORM)
    except ValueError:
        return
    raise AssertionError("negative observed must raise")


def test_price_with_custom_typical_table():
    custom = {AccommodationCategory.HOSTEL_DORM: 20.0}
    # 14 vs 20 -> ratio 0.70 -> 100
    assert score_price(14.0, AccommodationCategory.HOSTEL_DORM,
                       typical_table=custom) == 100.0


# ---------- score_location ----------

def test_location_at_center_is_100():
    assert score_location(0.0) == 100.0


def test_location_at_5km_is_0():
    assert score_location(5.0) == 0.0
    assert score_location(7.0) == 0.0


def test_location_linear_midway():
    # 2.5 km -> 50
    assert score_location(2.5) == 50.0


def test_location_rejects_negative():
    try:
        score_location(-0.1)
    except ValueError:
        return
    raise AssertionError("negative distance must raise")


# ---------- score_season ----------

def test_season_low_is_best():
    assert score_season(Season.LOW) == 100.0


def test_season_mid_is_above_neutral():
    assert score_season(Season.MID) == 75.0


def test_season_high_is_below_neutral():
    assert score_season(Season.HIGH) == 60.0


def test_season_peak_is_worst():
    assert score_season(Season.PEAK) == 40.0


def test_season_none_is_neutral():
    assert score_season(None) == 50.0


# ---------- score_lodging_signal ----------

def test_lodging_red_is_best():
    assert score_lodging_signal(LodgingColor.RED) == 100.0


def test_lodging_yellow_is_strong():
    assert score_lodging_signal(LodgingColor.YELLOW) == 75.0


def test_lodging_green_is_neutral():
    assert score_lodging_signal(LodgingColor.GREEN) == 50.0


def test_lodging_none_is_neutral():
    assert score_lodging_signal(None) == 50.0


# ---------- score_option overall ----------

def test_option_overall_with_best_inputs():
    breakdown = score_option(
        observed_usd=10.0,                                # under typical
        category=AccommodationCategory.HOSTEL_DORM,
        distance_to_center_km=0.0,                        # center
        season=Season.LOW,                                # best
        lodging_color=LodgingColor.RED,                   # best
    )
    assert breakdown.price == 100.0
    assert breakdown.location == 100.0
    assert breakdown.season == 100.0
    assert breakdown.lodging_signal == 100.0
    assert breakdown.overall == 100.0


def test_option_overall_with_worst_inputs():
    breakdown = score_option(
        observed_usd=25.0,                                # well above typical 15
        category=AccommodationCategory.HOSTEL_DORM,
        distance_to_center_km=8.0,                        # far
        season=Season.PEAK,                               # worst
        lodging_color=LodgingColor.GREEN,                 # weakest non-None
    )
    assert breakdown.price == 0.0
    assert breakdown.location == 0.0
    assert breakdown.season == 40.0
    assert breakdown.lodging_signal == 50.0
    # overall = 0 + 0 + 0.15*40 + 0.25*50 = 6 + 12.5 = 18.5
    assert breakdown.overall == 18.5


def test_option_overall_neutral_unknown_context():
    breakdown = score_option(
        observed_usd=15.0,                                # typical
        category=AccommodationCategory.HOSTEL_DORM,
        distance_to_center_km=2.5,                        # half
        season=None,
        lodging_color=None,
    )
    # price=50 location=50 season=50 lodging=50 -> overall=50
    assert breakdown.overall == 50.0


def test_option_overall_changes_with_lodging_signal():
    """Confirms Layer 4 plumbing actually moves India's score."""
    base = score_option(
        observed_usd=15.0,
        category=AccommodationCategory.HOSTEL_DORM,
        distance_to_center_km=2.5,
        season=Season.MID,
        lodging_color=None,
    )
    with_red = score_option(
        observed_usd=15.0,
        category=AccommodationCategory.HOSTEL_DORM,
        distance_to_center_km=2.5,
        season=Season.MID,
        lodging_color=LodgingColor.RED,
    )
    # RED (100) replaces neutral (50) on the lodging axis (weight 0.25).
    # Delta should be 0.25 * (100 - 50) = 12.5
    assert round(with_red.overall - base.overall, 4) == 12.5


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
    print(f"\nLayer 5 India scoring: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
