"""Smoke / verification tests for the Global Airfare Intelligence System.

Run as a plain script (no pytest required):
    python tests/test_smoke.py
Or with pytest:
    pytest -q

Confirms: every region pack parses, imports work, the placeholder
fetcher returns data, route comparison + classification work with mock
data, arrival rules downgrade late-night RED deals, and the scheduler /
heartbeat / Telegram handlers load. Fully hermetic — no live API calls.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _config():
    """Load config (activates the colombia region pack by default)."""
    from src.config import load_config

    return load_config()


def _offer(origin, dest, price, depart, dur_hours, stops=0):
    from src.flight_fetcher import FlightOffer

    return FlightOffer(
        origin, dest, price, depart,
        depart + timedelta(hours=dur_hours), "TestAir", stops,
    )


def _comparison(dest, direct_price, positioning_total=None,
                gateway="MIA", arrival_hour=12, config=None):
    from src.route_compare import RouteComparison, RouteOption, _choose_recommendation

    base = datetime(2026, 6, 1, 8, 0)
    direct = RouteOption(
        "direct", [_offer("BWI", dest, direct_price, base, 8, stops=1)]
    )
    comp = RouteComparison(destination=dest, direct=direct)
    if positioning_total is not None:
        leg1 = _offer("BWI", gateway, positioning_total * 0.4, base, 2.5)
        leg2_depart = datetime(2026, 6, 1, arrival_hour, 0) - timedelta(hours=4)
        leg2 = _offer(gateway, dest, positioning_total * 0.6, leg2_depart, 4)
        pos = RouteOption("positioning", [leg1, leg2], gateway=gateway)
        comp.positioning = pos
        comp.all_positioning = [pos]
    _choose_recommendation(comp, config)
    return comp


# --- tests -----------------------------------------------------------------

def test_env_example_exists():
    env = ROOT / ".env.example"
    assert env.is_file(), ".env.example is missing"
    text = env.read_text(encoding="utf-8")
    for key in ("TELEGRAM_BOT_TOKEN", "REGION_PACK", "FLIGHT_API_PROVIDER"):
        assert key in text, f"{key} missing from .env.example"


def test_core_imports():
    import src.region  # noqa: F401
    import src.config  # noqa: F401
    import src.flight_fetcher  # noqa: F401
    import src.route_compare  # noqa: F401
    import src.arrival_rules  # noqa: F401
    import src.deal_classifier  # noqa: F401
    import src.alert_formatter  # noqa: F401
    import src.storage  # noqa: F401
    import src.heartbeat_alerts  # noqa: F401
    import src.scheduler  # noqa: F401


def test_all_region_packs_parse():
    from src.region import CONFIGS_DIR, load_region_pack

    packs = sorted(CONFIGS_DIR.glob("*.yaml"))
    assert len(packs) >= 9, f"expected >=9 region packs, found {len(packs)}"
    for path in packs:
        pack = load_region_pack(str(path))
        assert pack.destinations, f"{path.name}: no destinations"
        assert pack.gateways, f"{path.name}: no gateways"
        assert pack.origin, f"{path.name}: no origin"


def test_config_loads_with_region():
    cfg = _config()
    assert cfg.region is not None, cfg.region_error
    assert cfg.region.slug == "colombia"
    assert cfg.red_min_savings_usd >= cfg.yellow_min_savings_usd


def test_placeholder_fetcher():
    from src.flight_fetcher import PlaceholderFlightFetcher

    _config()  # activate region
    fetcher = PlaceholderFlightFetcher()
    offers = fetcher.search("BWI", "BOG", date.today() + timedelta(days=21))
    assert offers and all(o.price_usd > 0 for o in offers)


def test_route_comparison_with_mock_data():
    from src.flight_fetcher import PlaceholderFlightFetcher
    from src.route_compare import compare_routes

    cfg = _config()
    comp = compare_routes(
        PlaceholderFlightFetcher(), "BOG", cfg, date.today() + timedelta(days=21)
    )
    assert comp.destination == "BOG"
    assert comp.direct is not None
    assert comp.recommended is not None and comp.recommended.total_price > 0


def test_deal_classifier_labels():
    from src.deal_classifier import DealColor, classify_route

    cfg = _config()
    green = classify_route(_comparison("CTG", 300, 270, config=cfg), cfg)
    assert green.color == DealColor.GREEN, green.color
    yellow = classify_route(_comparison("CTG", 300, 200, config=cfg), cfg)
    assert yellow.color == DealColor.YELLOW, yellow.color
    red = classify_route(_comparison("CTG", 450, 250, config=cfg), cfg)
    assert red.color == DealColor.RED, red.color


def test_arrival_rule_late_night_downgrade():
    from src.deal_classifier import DealColor, classify_route

    cfg = _config()
    # MDE carries arrival_rules in colombia.yaml — a 23:00 RED is capped.
    result = classify_route(
        _comparison("MDE", 500, 300, arrival_hour=23, config=cfg), cfg
    )
    assert result.color == DealColor.YELLOW, result.color
    assert result.arrival.is_late_night
    assert any("Downgraded" in n for n in result.classification.notes)


def test_scheduler_and_heartbeat_load():
    from src.flight_fetcher import PlaceholderFlightFetcher
    from src.heartbeat_alerts import HeartbeatManager
    from src.scheduler import run_full_scan, setup_jobs  # noqa: F401

    cfg = _config()
    heartbeat = HeartbeatManager(cfg, PlaceholderFlightFetcher())
    assert heartbeat.register("MDE") is True
    assert heartbeat.register("MDE") is False
    assert heartbeat.active_count() == 1


def test_full_scan_runs():
    from src.flight_fetcher import PlaceholderFlightFetcher
    from src.scheduler import run_full_scan

    cfg = _config()
    # Always use the placeholder here — smoke tests must never hit a live API.
    results = run_full_scan({"config": cfg, "fetcher": PlaceholderFlightFetcher()})
    assert len(results) == 6, "expected one result per Colombia destination"
    assert {r.color.value for r in results} <= {"GREEN", "YELLOW", "RED"}


def test_alert_formatter():
    from src.alert_formatter import (
        format_deal_alert,
        format_deals_list,
        format_positioning_report,
    )
    from src.deal_classifier import classify_route

    cfg = _config()
    result = classify_route(_comparison("CTG", 450, 250, config=cfg), cfg)
    assert "RED DEAL" in format_deal_alert(result)
    assert format_deals_list([result])
    assert format_positioning_report([result])


def test_skyscanner_itinerary_parsing():
    from src.flight_fetcher import _parse_skyscanner_itinerary

    sample = {
        "price": {"amount": 203, "currency": "USD"},
        "legs": [
            {
                "origin": "BWI", "destination": "BOG",
                "departure": "2026-06-09T10:33:00",
                "arrival": "2026-06-09T19:15:00",
                "stopCount": 1,
                "carriers": [{"name": "Delta", "logoUrl": "x"}],
            }
        ],
    }
    offer = _parse_skyscanner_itinerary(sample, "BWI", "BOG")
    assert offer is not None and offer.price_usd == 203.0 and offer.stops == 1
    assert _parse_skyscanner_itinerary({"bad": "data"}, "BWI", "BOG") is None


def test_command_slug_handles_accents():
    try:
        import telegram  # noqa: F401
    except ImportError:
        print("    (skipped: python-telegram-bot not installed)")
        return
    from src.telegram_handlers import command_slug

    assert command_slug("Bogotá") == "bogota"
    assert command_slug("Santa Marta") == "santamarta"
    assert command_slug("São Paulo") == "saopaulo"


def test_telegram_handlers_load():
    try:
        import telegram  # noqa: F401
    except ImportError:
        print("    (skipped: python-telegram-bot not installed)")
        return
    import src.telegram_handlers as handlers

    assert hasattr(handlers, "register_handlers")


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
