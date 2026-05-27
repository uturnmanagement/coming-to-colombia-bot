"""Layer 3 — Echo (price-context) tests.

Covers:
    - PriceBand thresholds (great/good/normal/high)
    - Echo report shape against SpecialistReport schema
    - Echo's verdict_input keys (price_position_label + price_position_pct)
    - lodging_signal is None (Layer 4 reservation)
    - typical-price fallback when region pack unavailable
    - destination extraction from positioning route signatures

Runnable directly:
    python tests/test_layer3_echo.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.echo import Echo, DEFAULT_TYPICAL_PRICE_USD
from agents.oakstreet import AlertEvent
from agents.specialist_report import Status, VERDICT_KEYS
from intel.price_context import PriceBand, classify_price_position


T0 = datetime(2026, 5, 27, 10, 0, 0)


def _event(price=285.0, route="BWI->BOG direct"):
    return AlertEvent(
        deal_id="DEAL-E3",
        color="red",
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


# ---------- classifier ----------

def test_classifier_great_threshold():
    band = PriceBand(typical_usd=300.0)
    assert classify_price_position(200.0, band).label == "great"


def test_classifier_good_threshold():
    band = PriceBand(typical_usd=300.0)
    assert classify_price_position(250.0, band).label == "good"


def test_classifier_normal_threshold():
    band = PriceBand(typical_usd=300.0)
    assert classify_price_position(300.0, band).label == "normal"
    assert classify_price_position(320.0, band).label == "normal"


def test_classifier_high_threshold():
    band = PriceBand(typical_usd=300.0)
    assert classify_price_position(380.0, band).label == "high"


def test_classifier_rejects_zero_band():
    try:
        classify_price_position(200, PriceBand(typical_usd=0))
    except ValueError:
        return
    raise AssertionError("zero band must raise")


# ---------- Echo specialist ----------

def test_echo_report_is_typed_specialist_report():
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=285))
    assert rpt.agent == "echo"
    assert rpt.deal_id == "DEAL-E3"
    assert 0.0 <= rpt.confidence <= 1.0


def test_echo_verdict_input_keys_known():
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=285))
    assert set(rpt.verdict_input).issubset(VERDICT_KEYS)
    assert "price_position_label" in rpt.verdict_input
    assert "price_position_pct" in rpt.verdict_input
    assert "lodging_signal" in rpt.verdict_input
    assert rpt.verdict_input["lodging_signal"] is None


def test_echo_great_label():
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=200))
    assert rpt.verdict_input["price_position_label"] == "great"


def test_echo_normal_label():
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=330))
    assert rpt.verdict_input["price_position_label"] == "normal"


def test_echo_lodging_signal_reserved():
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=285))
    assert "lodging-hook-reserved" in rpt.flags
    assert rpt.payload["lodging_signal"] is None


def test_echo_falls_back_when_destination_missing():
    rpt = Echo({}).analyze(_event(price=285))
    assert rpt.status is Status.PARTIAL
    assert rpt.payload["typical_price_usd"] == DEFAULT_TYPICAL_PRICE_USD


def test_echo_extracts_dest_from_positioning_route():
    rpt = Echo({"BOG": 330.0}).analyze(_event(route="BWI->MIA->BOG"))
    assert rpt.payload["destination"] == "BOG"


def test_echo_report_serializable():
    import json
    rpt = Echo({"BOG": 330.0}).analyze(_event(price=285))
    parsed = json.loads(rpt.to_json())
    assert parsed["agent"] == "echo"
    assert parsed["payload"]["label"] in ("great", "good", "normal", "high")


# ---------- runner ----------

def _all_tests():
    return [(name, obj) for name, obj in globals().items()
            if name.startswith("test_") and callable(obj)]


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
    print(f"\nLayer 3 echo: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
