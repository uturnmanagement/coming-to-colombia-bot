"""Layer 4 — RED/YELLOW/GREEN scoring tests.

Covers:
    - Pure raw-pct calculation (no weighting)
    - Weighted-pct = raw * season_multiplier
    - GREEN/YELLOW/RED boundaries exactly at 8% and 15% (weighted)
    - Weighting disabled collapses multiplier to 1.0
    - PEAK season requires bigger drops to reach YELLOW / RED
    - LOW season amplifies — smaller drops still trigger YELLOW
    - Edge cases: observed == baseline (raw 0 → GREEN), observed > baseline
    - Invalid inputs raise

Runnable directly:
    python tests/test_layer4_scoring.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.lodging import (
    LodgingColor,
    LodgingThresholds,
    Season,
    score_observation,
)


# Sample dates per season — picked away from window boundaries.
MID_DAY = date(2026, 2, 14)       # multiplier 1.00
LOW_DAY = date(2026, 4, 25)       # multiplier 1.20
HIGH_DAY = date(2026, 7, 4)       # multiplier 0.85
PEAK_DAY = date(2026, 12, 20)     # multiplier 0.75


# ---------- raw math ----------

def test_raw_pct_below_basic():
    s = score_observation(
        observed_usd=92.0, baseline_usd=100.0, on_date=MID_DAY,
        weighting_enabled=False,
    )
    assert s.raw_pct_below == 8.0
    assert s.weighted_pct_below == 8.0
    assert s.season_multiplier_applied == 1.0


def test_observed_equals_baseline_is_green():
    s = score_observation(
        observed_usd=100.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    assert s.color is LodgingColor.GREEN
    assert s.raw_pct_below == 0.0


def test_observed_above_baseline_is_green():
    s = score_observation(
        observed_usd=120.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    assert s.color is LodgingColor.GREEN
    assert s.raw_pct_below < 0


def test_invalid_baseline_raises():
    try:
        score_observation(
            observed_usd=90.0, baseline_usd=0, on_date=MID_DAY,
        )
    except ValueError:
        return
    raise AssertionError("baseline=0 must raise")


def test_invalid_observed_raises():
    try:
        score_observation(
            observed_usd=-1, baseline_usd=100, on_date=MID_DAY,
        )
    except ValueError:
        return
    raise AssertionError("observed=-1 must raise")


# ---------- spec thresholds, MID season (multiplier 1.0) ----------

def test_mid_under_8_is_green():
    s = score_observation(
        observed_usd=93.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    # raw 7.0%, weighted 7.0% → GREEN.
    assert s.color is LodgingColor.GREEN


def test_mid_exactly_8_is_yellow():
    s = score_observation(
        observed_usd=92.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    # raw 8.0% → YELLOW (spec: ">= 8%").
    assert s.color is LodgingColor.YELLOW


def test_mid_just_under_15_is_yellow():
    s = score_observation(
        observed_usd=86.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    # raw 14.0% → YELLOW.
    assert s.color is LodgingColor.YELLOW


def test_mid_exactly_15_is_red():
    s = score_observation(
        observed_usd=85.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    # raw 15.0% → RED.
    assert s.color is LodgingColor.RED


def test_mid_well_above_15_is_red():
    s = score_observation(
        observed_usd=70.0, baseline_usd=100.0, on_date=MID_DAY,
    )
    assert s.color is LodgingColor.RED


# ---------- season weighting effects ----------

def test_low_season_amplifies_small_drop_to_yellow():
    # raw 7% in LOW → weighted 7 * 1.2 = 8.4 → YELLOW (would be GREEN in MID).
    s = score_observation(
        observed_usd=93.0, baseline_usd=100.0, on_date=LOW_DAY,
    )
    assert s.season is Season.LOW
    assert s.color is LodgingColor.YELLOW
    assert round(s.weighted_pct_below, 4) == 8.4


def test_peak_season_attenuates_yellow_to_green():
    # raw 9% in PEAK → weighted 9 * 0.75 = 6.75 → GREEN.
    s = score_observation(
        observed_usd=91.0, baseline_usd=100.0, on_date=PEAK_DAY,
    )
    assert s.season is Season.PEAK
    assert s.color is LodgingColor.GREEN


def test_high_season_attenuates_red_to_yellow():
    # raw 16% in HIGH → weighted 16 * 0.85 = 13.6 → YELLOW.
    s = score_observation(
        observed_usd=84.0, baseline_usd=100.0, on_date=HIGH_DAY,
    )
    assert s.season is Season.HIGH
    assert s.color is LodgingColor.YELLOW


def test_peak_red_requires_20pct_raw():
    # PEAK multiplier 0.75 — to hit weighted 15, raw must be 20.
    s = score_observation(
        observed_usd=80.0, baseline_usd=100.0, on_date=PEAK_DAY,
    )
    assert s.color is LodgingColor.RED


def test_weighting_disabled_uses_raw_pct():
    s = score_observation(
        observed_usd=88.0, baseline_usd=100.0, on_date=PEAK_DAY,
        weighting_enabled=False,
    )
    assert s.season_multiplier_applied == 1.0
    assert s.raw_pct_below == 12.0
    # Without weighting, raw 12% → YELLOW.
    assert s.color is LodgingColor.YELLOW


# ---------- custom thresholds ----------

def test_custom_thresholds_respected():
    th = LodgingThresholds(yellow_pct=5.0, red_pct=10.0)
    s = score_observation(
        observed_usd=92.0, baseline_usd=100.0, on_date=MID_DAY,
        thresholds=th,
    )
    # raw 8% with tighter thresholds → YELLOW (>5), under RED (10).
    assert s.color is LodgingColor.YELLOW


def test_thresholds_must_be_ordered():
    try:
        LodgingThresholds(yellow_pct=15.0, red_pct=10.0)
    except ValueError:
        return
    raise AssertionError("yellow > red must raise")


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
    print(f"\nLayer 4 scoring: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
