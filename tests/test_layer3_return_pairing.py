"""Layer 3 — Return Pairing (Delta + intel/return_pairing) tests.

Covers:
    - window list shape (4/7/10/14/21/30/42/50)
    - date arithmetic (outbound_depart + days)
    - pairing engine pricing path
    - missing-data degradation (NO_DATA / PARTIAL)
    - Delta specialist report shape against the SpecialistReport schema
    - verdict_input keys present and within VERDICT_KEYS

Runnable directly:
    python tests/test_layer3_return_pairing.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.delta import Delta, placeholder_return_fetcher
from agents.oakstreet import AlertEvent
from agents.specialist_report import Status, VERDICT_KEYS
from intel.return_pairing import (
    RETURN_WINDOWS_DAYS,
    estimate_pairing,
    generate_windows,
)


T0 = datetime(2026, 5, 27, 10, 0, 0)


def _event(price=285.0, route="BWI->BOG direct", dest_offset_h=72.0):
    return AlertEvent(
        deal_id="DEAL-D3",
        color="red",
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=dest_offset_h),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


# ---------- canonical window list ----------

def test_return_windows_list_exact():
    assert RETURN_WINDOWS_DAYS == (4, 7, 10, 14, 21, 30, 42, 50)


def test_generate_windows_dates():
    out = date(2026, 6, 1)
    pairs = generate_windows(out)
    assert [d for d, _ in pairs] == list(RETURN_WINDOWS_DAYS)
    assert pairs[0] == (4, date(2026, 6, 5))
    assert pairs[-1] == (50, date(2026, 7, 21))


def test_generate_windows_rejects_nonpositive():
    try:
        generate_windows(date(2026, 6, 1), windows=(0, 7))
    except ValueError:
        return
    raise AssertionError("non-positive window should raise")


# ---------- pairing engine ----------

def test_estimate_pairing_full_coverage():
    est = estimate_pairing(
        origin="BWI", destination="BOG",
        outbound_depart=date(2026, 6, 1),
        outbound_price_usd=285,
        fetcher=lambda *_: 240.0,
    )
    assert len(est.options) == len(RETURN_WINDOWS_DAYS)
    assert all(o.round_trip_total_usd == 525.0 for o in est.options)
    assert est.best_option.round_trip_total_usd == 525.0


def test_estimate_pairing_no_data():
    est = estimate_pairing(
        origin="BWI", destination="BOG",
        outbound_depart=date(2026, 6, 1),
        outbound_price_usd=285,
        fetcher=lambda *_: None,
    )
    assert all(o.round_trip_total_usd is None for o in est.options)
    assert est.best_option is None


def test_estimate_pairing_partial():
    def f(origin, dest, ret_date):
        return 200.0 if ret_date.day % 2 == 0 else None

    est = estimate_pairing(
        origin="BWI", destination="BOG",
        outbound_depart=date(2026, 6, 1),
        outbound_price_usd=300,
        fetcher=f,
    )
    priced = [o for o in est.options if o.round_trip_total_usd is not None]
    assert 0 < len(priced) < len(est.options)


# ---------- Delta specialist report shape ----------

def test_delta_report_is_typed_specialist_report():
    rpt = Delta().analyze(_event())
    assert rpt.agent == "delta"
    assert rpt.status in (Status.OK, Status.PARTIAL, Status.STUB, Status.NO_DATA)
    assert 0.0 <= rpt.confidence <= 1.0
    assert rpt.deal_id == "DEAL-D3"


def test_delta_report_payload_carries_all_windows():
    rpt = Delta().analyze(_event())
    options = rpt.payload["options"]
    assert len(options) == len(RETURN_WINDOWS_DAYS)
    assert [o["window_days"] for o in options] == list(RETURN_WINDOWS_DAYS)


def test_delta_report_verdict_input_keys_known():
    rpt = Delta().analyze(_event())
    assert set(rpt.verdict_input).issubset(VERDICT_KEYS)
    if rpt.verdict_input:
        assert "round_trip_est_usd" in rpt.verdict_input
        assert "best_return_window_days" in rpt.verdict_input


def test_delta_flags_placeholder():
    rpt = Delta().analyze(_event())
    assert "placeholder-fetcher" in rpt.flags


def test_delta_no_data_degrades():
    rpt = Delta(fetcher=lambda *_: None).analyze(_event())
    assert rpt.status is Status.NO_DATA
    assert rpt.confidence == 0.0
    assert rpt.verdict_input == {}


def test_delta_extracts_destination_from_positioning_route():
    evt = _event(route="BWI->MIA->BOG")
    rpt = Delta().analyze(evt)
    assert rpt.payload["destination"] == "BOG"


def test_delta_report_serializable():
    """SpecialistReport.to_json must produce parseable JSON for storage."""
    import json
    rpt = Delta().analyze(_event())
    parsed = json.loads(rpt.to_json())
    assert parsed["agent"] == "delta"
    assert "options" in parsed["payload"]


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
    print(f"\nLayer 3 return pairing: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
