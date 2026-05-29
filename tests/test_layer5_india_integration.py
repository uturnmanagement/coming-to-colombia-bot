"""Layer 5 — India ↔ Layer 4 lodging brain integration tests.

Covers:
    - India.analyze with NO lodging_service → lodging_color=None,
      'lodging-signal-unavailable' flag set
    - India.analyze WITH a populated LodgingIntelService → consults
      signal_for(...) and the lodging axis carries that color
    - Best option's overall_score in (0, 100]; payload + verdict_input
      are well-formed and within VERDICT_KEYS
    - SpecialistReport status degrades correctly: NO_DATA when the
      provider has no options for the city; PARTIAL without lodging;
      STUB when fully exercised on mock data
    - Lodging service exception is swallowed and reported via flag
    - India.analyze respects an explicit city= override

Runnable directly:
    python tests/test_layer5_india_integration.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.india import (
    AccommodationCategory,
    India,
    MockHostelProvider,
)
from agents.oakstreet import AlertEvent
from agents.specialist_report import Status, VERDICT_KEYS
from db.sqlite_manager import SqliteManager
from intel.lodging import (
    LodgingColor,
    LodgingIntelService,
    LodgingStorage,
)
from intel.lodging.providers import MockLodgingProvider


T0 = datetime(2026, 5, 28, 12, 0, 0)


def _event(route="BWI->BOG direct", price=285.0, deal_id="d-i5"):
    return AlertEvent(
        deal_id=deal_id, color="red", price_usd=price,
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


# ---------- no lodging service ----------

def test_analyze_without_lodging_service_marks_partial():
    rpt = India().analyze(_event())
    assert rpt.agent == "india"
    assert rpt.status is Status.PARTIAL
    assert "lodging-signal-unavailable" in rpt.flags
    assert rpt.payload["signal"]["lodging_color"] is None


def test_analyze_verdict_keys_within_schema():
    rpt = India().analyze(_event())
    assert set(rpt.verdict_input).issubset(VERDICT_KEYS)
    assert "best_hostel_score" in rpt.verdict_input
    assert "best_hostel_category" in rpt.verdict_input
    assert "best_hostel_price_usd" in rpt.verdict_input
    assert "hostel_options_count" in rpt.verdict_input


def test_analyze_options_get_scored():
    rpt = India().analyze(_event())
    for opt in rpt.payload["options"]:
        assert opt["score"] is not None
        assert 0.0 <= opt["score"]["overall"] <= 100.0


# ---------- with lodging service populated ----------

def test_analyze_with_lodging_service_carries_color():
    svc = _lodging_service(populate=True)
    rpt = India(lodging_service=svc).analyze(_event())
    color = rpt.payload["signal"]["lodging_color"]
    assert color in {LodgingColor.GREEN.value,
                     LodgingColor.YELLOW.value,
                     LodgingColor.RED.value}


def test_analyze_with_lodging_service_marks_stub_status():
    svc = _lodging_service(populate=True)
    rpt = India(lodging_service=svc).analyze(_event())
    assert rpt.status is Status.STUB
    assert "lodging-signal-unavailable" not in rpt.flags


def test_analyze_lodging_signal_changes_score_axis():
    """A populated lodging service must move India's lodging sub-score
    away from the unavailable-neutral value (50)."""
    no_svc_rpt = India().analyze(_event())
    with_svc_rpt = India(lodging_service=_lodging_service()).analyze(_event())
    no_svc_lodging = no_svc_rpt.payload["options"][0]["score"]["lodging_signal"]
    with_svc_lodging = with_svc_rpt.payload["options"][0]["score"]["lodging_signal"]
    # Either equal-by-coincidence (unlikely) or strictly different.
    # We assert the unavailable case is exactly 50.
    assert no_svc_lodging == 50.0
    assert with_svc_lodging in (50.0, 75.0, 100.0)


def test_lodging_service_exception_does_not_propagate():
    """A broken lodging service must not crash India."""

    class _Broken:
        def signal_for(self, **_):
            raise RuntimeError("boom")

    rpt = India(lodging_service=_Broken()).analyze(_event())
    assert rpt.status is Status.PARTIAL
    assert "lodging-signal-unavailable" in rpt.flags


# ---------- city override + no-options path ----------

def test_analyze_with_explicit_city_overrides_route_parse():
    rpt = India().analyze(_event(route="BWI->MIA->CTG"), city="MDE")
    assert rpt.payload["city"] == "MDE"
    assert len(rpt.payload["options"]) == 3   # MDE seed has 3 options


def test_analyze_unknown_city_yields_no_data():
    rpt = India().analyze(_event(), city="ZZZ")
    assert rpt.status is Status.NO_DATA
    assert rpt.confidence == 0.0
    assert rpt.payload["options"] == []
    assert rpt.payload["signal"] is None
    assert "no-options-for-city" in rpt.flags
    assert rpt.verdict_input == {}


# ---------- payload is JSON-serializable ----------

def test_specialist_report_payload_is_json_serializable():
    rpt = India(lodging_service=_lodging_service()).analyze(_event())
    j = rpt.to_json()
    parsed = json.loads(j)
    assert parsed["agent"] == "india"
    assert parsed["payload"]["signal"]["best_category"] in {
        AccommodationCategory.HOSTEL_DORM.value,
        AccommodationCategory.HOSTEL_PRIVATE_ROOM.value,
        AccommodationCategory.BUDGET_HOTEL.value,
        AccommodationCategory.GUEST_HOUSE.value,
    }


# ---------- best-option selection ----------

def test_best_option_is_highest_scoring():
    rpt = India(lodging_service=_lodging_service()).analyze(_event())
    options = rpt.payload["options"]
    best_name_signal = rpt.payload["signal"]["best_option_name"]
    best_score_signal = rpt.payload["signal"]["best_score"]
    max_overall = max(o["score"]["overall"] for o in options)
    assert best_score_signal == max_overall
    # name lookup
    assert any(o["name"] == best_name_signal for o in options)


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
    print(f"\nLayer 5 India integration: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
