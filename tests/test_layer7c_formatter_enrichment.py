"""Layer 7C — Tier 1 Telegram formatter enrichment tests.

Verifies the itinerary-detail block added to the deal alert and the
destination detail view:

  1. Airline / carrier name
  2. Flight numbers (only when a provider supplied them)
  3. Connection airports (only when supplied)
  4. Route type (Direct or Positioning)
  5. Source badge (LIVE or MOCK)

Honesty constraints under test:
  - flight numbers / connections NEVER appear for placeholder data;
  - the source badge reads LIVE only when EVERY leg is provably live —
    placeholder, empty, or mixed provenance always degrades to MOCK.

Run as a plain script (no pytest required):
    python tests/test_layer7c_formatter_enrichment.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _config():
    from src.config import load_config

    return load_config()


def _offer(
    origin,
    dest,
    price,
    depart,
    dur_hours,
    *,
    airline="Avianca",
    stops=0,
    source="",
    flight_numbers=(),
    connections=(),
):
    from src.flight_fetcher import FlightOffer

    return FlightOffer(
        origin=origin,
        destination=dest,
        price_usd=price,
        depart_dt=depart,
        arrive_dt=depart + timedelta(hours=dur_hours),
        airline=airline,
        stops=stops,
        source=source,
        flight_numbers=tuple(flight_numbers),
        connections=tuple(connections),
    )


def _result_from_direct(offer, dest="BOG"):
    """Build a classified DealResult whose recommendation is the given direct leg."""
    from src.deal_classifier import classify_route
    from src.route_compare import RouteComparison, RouteOption, _choose_recommendation

    comp = RouteComparison(destination=dest, direct=RouteOption("direct", [offer]))
    _choose_recommendation(comp, _config())
    return classify_route(comp, _config())


def _result_positioning(leg1, leg2, gateway="MIA", dest="BOG"):
    from src.deal_classifier import classify_route
    from src.route_compare import RouteComparison, RouteOption, _choose_recommendation

    cfg = _config()
    pos = RouteOption("positioning", [leg1, leg2], gateway=gateway)
    comp = RouteComparison(destination=dest, positioning=pos, all_positioning=[pos])
    _choose_recommendation(comp, cfg)
    return classify_route(comp, cfg)


# --- tests -----------------------------------------------------------------

def test_placeholder_offer_is_mock_with_no_synthesized_detail():
    from src.alert_formatter import format_deal_alert

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    offer = _offer("BWI", "BOG", 420, base, 8, source="placeholder", stops=1)
    text = format_deal_alert(_result_from_direct(offer))

    assert "<b>Source:</b> MOCK" in text, text
    assert "<b>Route:</b> Direct" in text, text
    assert "<b>Airline:</b> Avianca" in text, text
    # Honesty: placeholder data must never fabricate itinerary detail.
    assert "Flights:" not in text, text
    assert "Connections:" not in text, text


def test_empty_source_defaults_to_mock():
    """Unknown provenance (legacy construction, source='') must read MOCK."""
    from src.alert_formatter import format_deal_alert

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    offer = _offer("BWI", "BOG", 420, base, 8, source="")
    text = format_deal_alert(_result_from_direct(offer))
    assert "<b>Source:</b> MOCK" in text, text
    assert "LIVE" not in text, text


def test_live_offer_renders_flight_numbers_and_connections():
    from src.alert_formatter import format_deal_alert

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    offer = _offer(
        "BWI", "BOG", 380, base, 8,
        airline="American", stops=1, source="live",
        flight_numbers=("AA245", "AA1190"), connections=("MIA",),
    )
    text = format_deal_alert(_result_from_direct(offer))

    assert "<b>Source:</b> LIVE" in text, text
    assert "<b>Airline:</b> American" in text, text
    assert "<b>Flights:</b> AA245, AA1190" in text, text
    assert "<b>Connections:</b> MIA" in text, text


def test_positioning_route_type_and_airline_chain():
    from src.alert_formatter import format_deal_alert

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    leg1 = _offer("BWI", "MIA", 120, base, 2.5, airline="Spirit", source="live")
    leg2 = _offer(
        "MIA", "BOG", 160, base + timedelta(hours=5), 4,
        airline="Avianca", source="live",
    )
    text = format_deal_alert(_result_positioning(leg1, leg2, gateway="MIA"))

    assert "<b>Route:</b> Positioning via" in text, text
    # Distinct carriers on each leg are chained in travel order.
    assert "Spirit → Avianca" in text, text


def test_mixed_live_and_placeholder_degrades_to_mock():
    """A single non-live leg forces the whole itinerary badge to MOCK."""
    from src.alert_formatter import format_deal_alert

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    leg1 = _offer("BWI", "MIA", 120, base, 2.5, source="live")
    leg2 = _offer(
        "MIA", "BOG", 160, base + timedelta(hours=5), 4, source="placeholder"
    )
    text = format_deal_alert(_result_positioning(leg1, leg2, gateway="MIA"))
    assert "<b>Source:</b> MOCK" in text, text


def test_destination_detail_also_enriched():
    from src.alert_formatter import format_destination_detail

    _config()
    base = datetime(2026, 7, 1, 8, 0)
    offer = _offer(
        "BWI", "BOG", 380, base, 8,
        airline="Delta", source="live", flight_numbers=("DL77",),
    )
    text = format_destination_detail(_result_from_direct(offer))
    assert "<b>Source:</b> LIVE" in text, text
    assert "<b>Flights:</b> DL77" in text, text


def test_enrichment_helpers_directly():
    from src.alert_formatter import (
        _airlines,
        _connections,
        _flight_numbers,
        _source_badge,
    )
    from src.route_compare import RouteOption

    base = datetime(2026, 7, 1, 8, 0)
    leg1 = _offer("BWI", "MIA", 120, base, 2.5, airline="JetBlue", source="live",
                  flight_numbers=("B6100",), connections=())
    leg2 = _offer("MIA", "BOG", 160, base + timedelta(hours=5), 4,
                  airline="Copa", source="live",
                  flight_numbers=("CM430",), connections=("PTY",))
    rec = RouteOption("positioning", [leg1, leg2], gateway="MIA")

    assert _source_badge(rec) == "LIVE"
    assert _airlines(rec) == "JetBlue → Copa"
    assert _flight_numbers(rec) == ["B6100", "CM430"]
    assert _connections(rec) == ["PTY"]

    leg2_mock = _offer("MIA", "BOG", 160, base + timedelta(hours=5), 4,
                       source="placeholder")
    rec_mixed = RouteOption("positioning", [leg1, leg2_mock], gateway="MIA")
    assert _source_badge(rec_mixed) == "MOCK"


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
