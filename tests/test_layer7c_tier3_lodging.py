"""Layer 7C — Tier 3 coupled-stay (lodging × return window) tests.

Tier 3 couples the lodging estimate to the chosen flight return window and
assembles a combined airfare + lodging trip total on the Oak Street briefing.
It is built from four pieces, exercised here bottom-up:

  1. lodging.pricing.estimator.discount_for_nights
       — piecewise length-of-stay discount for an arbitrary night count.
  2. lodging.pricing.estimator.stay_for_nights
       — pure pricing of a nightly band over N nights (inherits provenance).
  3. lodging.lodging_report.stay_window_estimate / render_stay_window_block
       — best-value stay priced for a return window + plain-text render.
  4. src.alert_formatter.format_lodging_badge
       — honesty token (LIVE only when explicitly not mock).
  5. agents.oakstreet.orchestrator.OakStreet._render_coupled_stay
       — the assembled TRIP TOTAL block, with clean independent degrade.

Honesty rule (mirrors Tier 1/2): Phase 6A lodging is MOCK and must always be
labelled; a LIVE airfare must never imply the lodging estimate is live.

Run as a plain script (no pytest required):
    .venv/bin/python tests/test_layer7c_tier3_lodging.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _delta_report(options):
    """A stand-in Delta specialist report carrying just a payload dict.

    _render_coupled_stay reads only `delta.payload`, so a SimpleNamespace
    mirrors the real SpecialistReport shape for these tests.
    """
    return SimpleNamespace(payload={"destination": "BOG", "options": list(options)})


def _option(*, window_days=14, total=520.0):
    """Minimal priced return-option dict (see _option_to_dict's shape)."""
    return {"window_days": window_days, "round_trip_total_usd": total}


# --- discount_for_nights ---------------------------------------------------

def test_discount_anchors_match_known_rates():
    from lodging.lodging_models import AccommodationType
    from lodging.pricing.estimator import (
        _DISCOUNTS,
        discount_for_nights,
    )

    for acc, (weekly, monthly) in _DISCOUNTS.items():
        assert discount_for_nights(acc, 1) == 0.0, acc
        assert abs(discount_for_nights(acc, 7) - weekly) < 1e-9, acc
        assert abs(discount_for_nights(acc, 30) - monthly) < 1e-9, acc
    # Sanity: Airbnb is the steepest, hostel dorm the shallowest.
    air = discount_for_nights(AccommodationType.AIRBNB, 30)
    dorm = discount_for_nights(AccommodationType.HOSTEL_DORM, 30)
    assert air > dorm, (air, dorm)


def test_discount_is_monotonic_and_capped_beyond_monthly():
    from lodging.lodging_models import AccommodationType
    from lodging.pricing.estimator import discount_for_nights

    acc = AccommodationType.AIRBNB
    prev = -1.0
    for n in range(1, 31):
        d = discount_for_nights(acc, n)
        assert d >= prev, (n, d, prev)   # non-decreasing across the range
        prev = d
    # Never extrapolates past the monthly rate.
    monthly = discount_for_nights(acc, 30)
    assert discount_for_nights(acc, 45) == monthly
    assert discount_for_nights(acc, 365) == monthly


def test_discount_handles_zero_and_unknown_type():
    from lodging.pricing.estimator import discount_for_nights

    # An unknown accommodation type degrades to no discount (0/0 anchors).
    assert discount_for_nights("not-a-type", 14) == 0.0
    # Zero / negative nights clamp to a single night → no discount.
    from lodging.lodging_models import AccommodationType
    assert discount_for_nights(AccommodationType.AIRBNB, 0) == 0.0
    assert discount_for_nights(AccommodationType.AIRBNB, -5) == 0.0


# --- stay_for_nights -------------------------------------------------------

def test_stay_for_nights_single_night_no_discount():
    from lodging.lodging_models import (
        AccommodationType,
        LodgingEstimate,
        StayEstimate,
    )
    from lodging.pricing.estimator import stay_for_nights

    nightly = StayEstimate(nights=1, low_usd=10.0, high_usd=20.0, discount_pct=0.0)
    est = LodgingEstimate(
        city="Bogotá", accommodation=AccommodationType.AIRBNB,
        nightly=nightly, weekly=nightly, monthly=nightly,
        source="mock_v1", is_mock=True,
    )
    stay = stay_for_nights(est, 1)
    assert stay.nights == 1
    assert stay.discount_pct == 0.0
    assert stay.low_usd == 10.0 and stay.high_usd == 20.0


def test_stay_for_nights_applies_length_discount():
    from lodging.lodging_models import (
        AccommodationType,
        LodgingEstimate,
        StayEstimate,
    )
    from lodging.pricing.estimator import discount_for_nights, stay_for_nights

    nightly = StayEstimate(nights=1, low_usd=100.0, high_usd=200.0, discount_pct=0.0)
    est = LodgingEstimate(
        city="Bogotá", accommodation=AccommodationType.AIRBNB,
        nightly=nightly, weekly=nightly, monthly=nightly,
        source="mock_v1", is_mock=True,
    )
    stay = stay_for_nights(est, 7)
    disc = discount_for_nights(AccommodationType.AIRBNB, 7)
    factor = 7 * (1.0 - disc)
    assert stay.nights == 7
    assert abs(stay.low_usd - round(100.0 * factor, 2)) < 1e-6, stay
    assert abs(stay.high_usd - round(200.0 * factor, 2)) < 1e-6, stay
    # A 7-night stay is cheaper than 7× the nightly rate (discount applied).
    assert stay.high_usd < 200.0 * 7


def test_stay_for_nights_clamps_nonpositive():
    from lodging.lodging_models import (
        AccommodationType,
        LodgingEstimate,
        StayEstimate,
    )
    from lodging.pricing.estimator import stay_for_nights

    nightly = StayEstimate(nights=1, low_usd=10.0, high_usd=20.0, discount_pct=0.0)
    est = LodgingEstimate(
        city="Bogotá", accommodation=AccommodationType.BUDGET_HOTEL,
        nightly=nightly, weekly=nightly, monthly=nightly,
        source="mock_v1", is_mock=True,
    )
    assert stay_for_nights(est, 0).nights == 1
    assert stay_for_nights(est, -3).nights == 1


# --- stay_window_estimate --------------------------------------------------

def test_stay_window_estimate_supported_city():
    from lodging.lodging_report import StayWindowEstimate, stay_window_estimate

    est = stay_window_estimate("BOG", 14)
    assert isinstance(est, StayWindowEstimate)
    assert est.city == "Bogotá"
    assert est.nights == 14
    assert est.is_mock is True                 # Phase 6A is mock
    assert est.low_usd <= est.high_usd
    assert est.accommodation_label             # best-value label is populated
    # mid is the midpoint of the band.
    assert abs(est.mid_usd - round((est.low_usd + est.high_usd) / 2.0, 2)) < 1e-6


def test_stay_window_estimate_unsupported_or_invalid_returns_none():
    from lodging.lodging_report import stay_window_estimate

    assert stay_window_estimate("ZZZ", 14) is None     # not a desk city
    assert stay_window_estimate(None, 14) is None       # no code
    assert stay_window_estimate("BOG", 0) is None       # non-positive nights
    assert stay_window_estimate("BOG", -7) is None


def test_stay_window_estimate_nights_drive_pricing():
    from lodging.lodging_report import stay_window_estimate

    short = stay_window_estimate("BOG", 3)
    long = stay_window_estimate("BOG", 21)
    # More nights → higher total even after the length-of-stay discount.
    assert long.mid_usd > short.mid_usd, (short.mid_usd, long.mid_usd)


# --- render_stay_window_block ----------------------------------------------

def test_render_stay_window_block_labels_mock():
    from lodging.lodging_report import render_stay_window_block, stay_window_estimate

    block = render_stay_window_block(stay_window_estimate("BOG", 14))
    assert "[MOCK]" in block, block
    assert "STAY FOR YOUR RETURN WINDOW" in block, block
    assert "Bogotá" in block, block
    assert "14 nights" in block, block
    assert "mock estimate (Phase 6A)" in block, block   # honesty disclaimer
    assert "Best value:" in block, block


def test_render_stay_window_block_shows_discount_when_present():
    from lodging.lodging_report import render_stay_window_block, stay_window_estimate

    # A 21-night stay always carries a non-zero length-of-stay discount.
    block = render_stay_window_block(stay_window_estimate("BOG", 21))
    assert "length-of-stay" in block, block


# --- format_lodging_badge --------------------------------------------------

def test_format_lodging_badge_honesty():
    from src.alert_formatter import format_lodging_badge

    assert format_lodging_badge(False) == "LIVE"   # explicitly not mock
    assert format_lodging_badge(True) == "MOCK"
    assert format_lodging_badge(None) == "MOCK"     # unknown provenance → MOCK
    assert format_lodging_badge("") == "MOCK"       # truthiness must not matter


# --- OakStreet._render_coupled_stay ----------------------------------------

def _oak():
    from agents.oakstreet.orchestrator import OakStreet

    # _render_coupled_stay touches neither db nor dispatcher.
    return OakStreet(db=None, dispatcher=None)


def test_coupled_stay_full_block():
    ok = _oak()
    reports = {"delta": _delta_report([_option(window_days=14, total=520.0)])}
    block = ok._render_coupled_stay(reports, "BOG")
    assert block is not None
    assert "TRIP TOTAL · airfare + lodging est." in block, block
    assert "14 nights" in block, block
    assert "airfare round-trip $520" in block, block
    # Lodging keeps its own MOCK badge even with a (here mock) airfare.
    assert "lodging MOCK" in block, block
    assert "<pre>" in block and "</pre>" in block, block
    assert "STAY FOR YOUR RETURN WINDOW" in block, block


def test_coupled_stay_combined_total_is_airfare_plus_lodging_mid():
    from lodging.lodging_report import stay_window_estimate

    ok = _oak()
    airfare = 520.0
    nights = 14
    reports = {"delta": _delta_report([_option(window_days=nights, total=airfare)])}
    block = ok._render_coupled_stay(reports, "BOG")

    est = stay_window_estimate("BOG", nights)
    combined = round(airfare + est.mid_usd, 2)
    assert f"~${combined:,.0f}" in block, (block, combined)


def test_coupled_stay_follows_cheapest_priced_window():
    ok = _oak()
    # The cheapest priced option (21 nights @ $410) must drive the window,
    # not the first-listed option.
    reports = {"delta": _delta_report([
        _option(window_days=7, total=900.0),
        _option(window_days=21, total=410.0),
    ])}
    block = ok._render_coupled_stay(reports, "BOG")
    assert "21 nights" in block, block
    assert "airfare round-trip $410" in block, block


def test_coupled_stay_degrades_without_delta():
    ok = _oak()
    assert ok._render_coupled_stay({}, "BOG") is None
    assert ok._render_coupled_stay({"delta": None}, "BOG") is None


def test_coupled_stay_degrades_without_priced_return():
    ok = _oak()
    unpriced = {"window_days": 14, "round_trip_total_usd": None}
    reports = {"delta": _delta_report([unpriced])}
    assert ok._render_coupled_stay(reports, "BOG") is None
    # No options at all → also clean None.
    assert ok._render_coupled_stay({"delta": _delta_report([])}, "BOG") is None


def test_coupled_stay_degrades_for_unsupported_destination():
    ok = _oak()
    reports = {"delta": _delta_report([_option()])}
    # A priced return but a non-desk city → no lodging estimate → None.
    assert ok._render_coupled_stay(reports, "ZZZ") is None


def test_coupled_stay_requires_window_days():
    ok = _oak()
    # Priced, but the window length is missing → cannot price a stay.
    no_window = {"window_days": None, "round_trip_total_usd": 500.0}
    reports = {"delta": _delta_report([no_window])}
    assert ok._render_coupled_stay(reports, "BOG") is None


# --- runner ----------------------------------------------------------------

def run_all() -> bool:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {test.__name__}: {exc}")
            import traceback

            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
