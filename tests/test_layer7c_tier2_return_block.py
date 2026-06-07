"""Layer 7C — Tier 2 (Interpretation B) return-block enrichment tests.

Verifies the itinerary-detail block appended to the return-pairing section
of the Oak Street Telegram briefing:

  1. Airline / carrier name
  2. Flight numbers (only when a provider supplied them)
  3. Connection airports (only when supplied)
  4. Route type
  5. LIVE / MOCK badge (per option)
  6. Optional booking link — BONUS, shown only when the option is live AND
     carries a validated http(s) URL; never on placeholder/MOCK data.

These run against the Delta payload dict shape (the JSON-safe option dicts
produced by agents/delta/specialist.py:_option_to_dict).

Run as a plain script (no pytest required):
    python tests/test_layer7c_tier2_return_block.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _option(
    *,
    window_days=14,
    total=520.0,
    source="placeholder",
    airline="Avianca",
    route_type="direct",
    flight_numbers=(),
    connections=(),
    booking_url="",
):
    """Build one return-option dict mirroring _option_to_dict's shape."""
    return {
        "window_days": window_days,
        "return_date": "2026-07-15",
        "return_price_usd": round(total - 200.0, 2),
        "round_trip_total_usd": total,
        "confidence": 1.0,
        "airline": airline,
        "stops": 0 if route_type == "direct" else 1,
        "route_type": route_type,
        "source": source,
        "flight_numbers": list(flight_numbers),
        "connections": list(connections),
        "booking_url": booking_url,
        "color": "RED",
    }


def _payload(options):
    return {"destination": "BOG", "options": list(options)}


# --- tests -----------------------------------------------------------------

def test_placeholder_best_is_mock_no_synthesized_detail():
    from src.alert_formatter import format_return_block

    block = "\n".join(format_return_block(_payload([_option(source="placeholder")])))
    assert "<b>Source:</b> MOCK" in block, block
    assert "<b>Return route:</b> direct" in block, block
    assert "<b>Airline:</b> Avianca" in block, block
    # Honesty: placeholder data carries no flight numbers / connections / link.
    assert "Flights:" not in block, block
    assert "Connections:" not in block, block
    assert "Book this return" not in block, block


def test_live_best_renders_flights_connections_and_link():
    from src.alert_formatter import format_return_block

    opt = _option(
        source="live", airline="Copa", route_type="one stop",
        flight_numbers=("CM430", "CM9"), connections=("PTY",),
        booking_url="https://www.skyscanner.net/transport/d/abc123",
    )
    block = "\n".join(format_return_block(_payload([opt])))
    assert "<b>Source:</b> LIVE" in block, block
    assert "<b>Airline:</b> Copa" in block, block
    assert "<b>Flights:</b> CM430, CM9" in block, block
    assert "<b>Connections:</b> PTY" in block, block
    assert '<a href="https://www.skyscanner.net/transport/d/abc123">Book this return</a>' in block, block


def test_best_is_cheapest_priced_option():
    from src.alert_formatter import format_return_block

    cheap = _option(window_days=21, total=410.0, source="live", airline="JetBlue")
    pricey = _option(window_days=7, total=900.0, source="live", airline="Delta")
    unpriced = _option(window_days=30, source="live")
    unpriced["round_trip_total_usd"] = None
    block = "\n".join(format_return_block(_payload([pricey, unpriced, cheap])))
    # The cheapest priced option (JetBlue, 410) drives the block.
    assert "<b>Airline:</b> JetBlue" in block, block
    assert "Delta" not in block, block


def test_no_priced_options_returns_empty():
    from src.alert_formatter import format_return_block

    unpriced = _option(source="live")
    unpriced["round_trip_total_usd"] = None
    assert format_return_block(_payload([unpriced])) == []
    assert format_return_block(_payload([])) == []


def test_booking_link_requires_live_source():
    from src.alert_formatter import _ret_booking_link

    # Placeholder with a URL present must NOT yield a link.
    assert _ret_booking_link(
        _option(source="placeholder",
                booking_url="https://example.com/book")
    ) is None


def test_booking_link_url_validation():
    from src.alert_formatter import _is_safe_booking_url, _ret_booking_link

    assert _is_safe_booking_url("https://a.com/x")
    assert _is_safe_booking_url("http://a.com/x")
    assert not _is_safe_booking_url("")
    assert not _is_safe_booking_url("ftp://a.com/x")
    assert not _is_safe_booking_url("javascript:alert(1)")
    assert not _is_safe_booking_url("https://")            # scheme only, no host
    assert not _is_safe_booking_url('https://a.com/"onclick')  # quote -> unsafe
    assert not _is_safe_booking_url("https://a.com/ space")    # whitespace -> unsafe
    assert not _is_safe_booking_url("https://a.com/<b>")       # angle bracket -> unsafe

    # A live option with an unsafe URL renders no link (never raw-injected).
    assert _ret_booking_link(
        _option(source="live", booking_url='https://a.com/"x')
    ) is None


def test_mixed_provenance_link_only_on_live_best():
    from src.alert_formatter import format_return_block

    # Cheapest is a placeholder fallback day (no link); a pricier day is live
    # with a URL. The block follows the CHEAPEST priced option, so it stays
    # MOCK with no link — provenance is judged per the actual best option.
    cheap_mock = _option(window_days=10, total=400.0, source="placeholder")
    pricey_live = _option(
        window_days=21, total=600.0, source="live",
        booking_url="https://book.example.com/x",
    )
    block = "\n".join(format_return_block(_payload([cheap_mock, pricey_live])))
    assert "<b>Source:</b> MOCK" in block, block
    assert "Book this return" not in block, block


def test_amadeus_live_without_url_shows_live_no_link():
    """Amadeus is live but never populates booking_url — badge LIVE, no link."""
    from src.alert_formatter import format_return_block

    opt = _option(source="live", airline="American",
                  flight_numbers=("AA245",), booking_url="")
    block = "\n".join(format_return_block(_payload([opt])))
    assert "<b>Source:</b> LIVE" in block, block
    assert "<b>Flights:</b> AA245" in block, block
    assert "Book this return" not in block, block


def test_orchestrator_delta_section_includes_enrichment():
    """Smoke: the briefing's Delta section now carries the enrichment lines."""
    from agents.delta import Delta, make_placeholder_offer_fetcher
    from src.config import load_config

    load_config()  # activate the colombia region pack for the placeholder fetcher
    delta = Delta(fetcher=make_placeholder_offer_fetcher(), windows=(7, 14, 21))

    # Minimal AlertEvent the specialist consumes (see agents.oakstreet).
    from datetime import datetime
    from agents.oakstreet import AlertEvent

    event = AlertEvent(
        deal_id="BWI-BOG-T2",
        color="red",
        price_usd=320.0,
        route_signature="BWI->BOG direct",
        departure_at=datetime(2026, 7, 1, 9, 0),
        observed_at=datetime(2026, 6, 7, 9, 0),
        summary="BWI->BOG $320",
    )
    report = delta.analyze(event)

    from src.alert_formatter import format_return_block

    block = "\n".join(format_return_block(report.payload))
    # Placeholder fetcher → MOCK badge, airline present, no fabricated link.
    assert "<b>Source:</b> MOCK" in block, block
    assert "<b>Airline:</b>" in block, block
    assert "Book this return" not in block, block


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
