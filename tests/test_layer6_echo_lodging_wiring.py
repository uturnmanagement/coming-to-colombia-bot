"""Layer 6 — Echo ↔ LodgingIntelService wiring tests.

Covers:
    - Backward compatibility: Echo with NO lodging_service behaves
      exactly as Layer 3-5 (lodging_signal=None, 'lodging-hook-reserved')
    - Echo WITH a populated service + observed nightly price fills the
      reserved lodging_signal slot with a compact serializable dict and
      flags 'lodging-wired'
    - Echo wired but with no observed price / no baseline / a broken
      service degrades quietly to None + 'lodging-signal-unavailable'
    - verdict_input stays within VERDICT_KEYS and JSON-serializable
    - The lodging wiring does NOT change Echo's status (price-context
      math is unchanged)

Runnable directly:
    python tests/test_layer6_echo_lodging_wiring.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.echo import Echo
from agents.oakstreet import AlertEvent
from agents.specialist_report import Status, VERDICT_KEYS
from db.sqlite_manager import SqliteManager
from intel.lodging import LodgingColor, LodgingIntelService, LodgingStorage
from intel.lodging.providers import MockLodgingProvider


T0 = datetime(2026, 5, 28, 12, 0, 0)
_COLORS = {LodgingColor.GREEN.value, LodgingColor.YELLOW.value, LodgingColor.RED.value}


def _event(price=285.0, route="BWI->BOG direct"):
    return AlertEvent(
        deal_id="DEAL-E6",
        color="red",
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


def _lodging_service(*, populate=True) -> LodgingIntelService:
    mgr = SqliteManager(":memory:", dry_run=True)
    svc = LodgingIntelService(
        storage=LodgingStorage(mgr),
        providers=[MockLodgingProvider()],
        lookback_days=14,
    )
    if populate:
        svc.refresh_observations(city="BOG", now=T0)
        svc.build_baseline(city="BOG", now=T0)
    return svc


# ---------- backward compatibility (no service) ----------

def test_no_service_keeps_reserved_behavior():
    rpt = Echo({"BOG": 330.0}).analyze(_event())
    assert rpt.payload["lodging_signal"] is None
    assert rpt.verdict_input["lodging_signal"] is None
    assert "lodging-hook-reserved" in rpt.flags


def test_no_service_status_unchanged():
    ok = Echo({"BOG": 330.0}).analyze(_event())
    partial = Echo({}).analyze(_event())
    assert ok.status is Status.OK
    assert partial.status is Status.PARTIAL


# ---------- wired + populated ----------

def test_wired_fills_lodging_signal_dict():
    rpt = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(populate=True),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    sig = rpt.verdict_input["lodging_signal"]
    assert isinstance(sig, dict)
    assert sig["color"] in _COLORS
    assert "weighted_pct_below" in sig and "sample_size" in sig
    assert rpt.payload["lodging_signal"] == sig
    assert "lodging-wired" in rpt.flags
    assert "lodging-hook-reserved" not in rpt.flags


def test_wired_does_not_change_status():
    """Status reflects the price band only — wiring must not flip it."""
    plain = Echo({"BOG": 330.0}).analyze(_event())
    wired = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    assert wired.status is plain.status is Status.OK
    assert wired.confidence == plain.confidence


def test_wired_verdict_within_schema_and_serializable():
    rpt = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    assert set(rpt.verdict_input).issubset(VERDICT_KEYS)
    parsed = json.loads(rpt.to_json())
    assert parsed["agent"] == "echo"
    assert parsed["verdict_input"]["lodging_signal"]["color"] in _COLORS


# ---------- wired but signal unavailable ----------

def test_wired_without_observed_price_is_unavailable():
    rpt = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(),
        # lodging_observed_usd intentionally omitted
    ).analyze(_event())
    assert rpt.payload["lodging_signal"] is None
    assert "lodging-signal-unavailable" in rpt.flags


def test_wired_without_baseline_is_unavailable():
    rpt = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(populate=False),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    assert rpt.verdict_input["lodging_signal"] is None
    assert "lodging-signal-unavailable" in rpt.flags


def test_broken_service_does_not_crash_echo():
    class _Broken:
        def signal_for(self, **_):
            raise RuntimeError("boom")

    rpt = Echo(
        {"BOG": 330.0},
        lodging_service=_Broken(),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    assert rpt.payload["lodging_signal"] is None
    assert "lodging-signal-unavailable" in rpt.flags
    # price-context half still intact
    assert rpt.verdict_input["price_position_label"] in (
        "great", "good", "normal", "high"
    )


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
    print(f"\nLayer 6 Echo lodging wiring: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
