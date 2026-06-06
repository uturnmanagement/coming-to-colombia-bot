"""Phase 6A — Lodging Intelligence Layer tests.

Run as a plain script (no pytest required):
    python tests/test_lodging_layer.py

Hermetic — mock provider only, no network. Confirms: the four
accommodation types are estimated for each of the 15 registry cities; weekly
and monthly projections apply the expected length-of-stay discounts;
value ranking marks the cheapest option BEST VALUE; the Delta appendix
renders for supported destination codes and is empty for others; and the
future live providers are present but inert (STUB / is_live False).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lodging import (
    ACCOMMODATION_ORDER,
    AccommodationType,
    CITY_REGISTRY,
    LodgingEngine,
    SUPPORTED_CITIES,
    render_all_cities,
    render_delta_lodging_appendix,
)
from lodging.pricing.estimator import WEEKLY_NIGHTS, MONTHLY_NIGHTS, estimate_from_quote
from lodging.providers import FUTURE_LIVE_PROVIDERS, MockLodgingProvider
from lodging.providers.base import ProviderStatus

NOW = datetime(2026, 6, 4, 9, 0, 0)


def _check(label: str, cond: bool) -> None:
    if not cond:
        raise AssertionError(f"FAILED: {label}")
    print(f"  ok: {label}")


def test_all_cities_all_types() -> None:
    engine = LodgingEngine()
    for city in SUPPORTED_CITIES:
        summary = engine.summarize_city(city, now=NOW)
        types = {e.accommodation for e in summary.estimates}
        _check(f"{city}: all 4 accommodation types present",
               types == set(ACCOMMODATION_ORDER))
        _check(f"{city}: marked mock", summary.is_mock)


def test_length_of_stay_discounts() -> None:
    provider = MockLodgingProvider()
    result = provider.fetch_city("Medellín")
    _check("mock provider OK for Medellín", result.status is ProviderStatus.OK)
    for q in result.quotes:
        est = estimate_from_quote(q)
        # Weekly low must be cheaper than 7x nightly low (discount applied).
        _check(f"{q.accommodation.value}: weekly < 7x nightly",
               est.weekly.low_usd < q.low_usd * WEEKLY_NIGHTS)
        _check(f"{q.accommodation.value}: monthly < 30x nightly",
               est.monthly.low_usd < q.low_usd * MONTHLY_NIGHTS)
        _check(f"{q.accommodation.value}: monthly discount >= weekly discount",
               est.monthly.discount_pct >= est.weekly.discount_pct)


def test_value_ranking() -> None:
    engine = LodgingEngine()
    summary = engine.summarize_city("Cartagena", now=NOW)
    ranks = [e.value_rank for e in summary.estimates]
    _check("ranks are 1..4 in order", ranks == [1, 2, 3, 4])
    best = summary.best_value
    _check("best value is the dorm bed (cheapest)",
           best.accommodation is AccommodationType.HOSTEL_DORM)
    # Estimates are sorted ascending by nightly mid price.
    mids = [e.nightly.mid_usd for e in summary.estimates]
    _check("estimates sorted cheapest-first", mids == sorted(mids))


def test_delta_appendix_supported_and_unsupported() -> None:
    for code, city in (("MDE", "Medellín"), ("CTG", "Cartagena"), ("SMR", "Santa Marta")):
        block = render_delta_lodging_appendix(code, now=NOW)
        _check(f"{code}: appendix renders", bool(block))
        _check(f"{code}: appendix names {city}", city in block)
        _check(f"{code}: appendix labelled mock", "mock" in block.lower())
        _check(f"{code}: shows nightly/weekly/monthly headers",
               "Nightly" in block and "Weekly" in block and "Monthly" in block)
    # A non-Colombia / unmapped destination (e.g. Miami) yields no block.
    _check("MIA: appendix empty (unsupported city)",
           render_delta_lodging_appendix("MIA", now=NOW) == "")
    _check("None code: appendix empty",
           render_delta_lodging_appendix(None, now=NOW) == "")


def test_future_providers_inert() -> None:
    _check("three future live providers reserved", len(FUTURE_LIVE_PROVIDERS) == 3)
    for cls in FUTURE_LIVE_PROVIDERS:
        prov = cls()
        _check(f"{prov.name}: is_live False", prov.is_live is False)
        res = prov.fetch_city("Medellín")
        _check(f"{prov.name}: returns STUB (no network)",
               res.status is ProviderStatus.STUB)


# Phase 6A.1 — the full Colombia pilot city list, by airport code and tier.
EXPECTED_CITIES = {
    # code: (city, tier)
    "BOG": ("Bogotá", 1), "MDE": ("Medellín", 1), "CTG": ("Cartagena", 1),
    "CLO": ("Cali", 1), "BAQ": ("Barranquilla", 1), "SMR": ("Santa Marta", 1),
    "BGA": ("Bucaramanga", 2), "PEI": ("Pereira", 2), "AXM": ("Armenia", 2),
    "MZL": ("Manizales", 2),
    "CUC": ("Cúcuta", 3), "MTR": ("Montería", 3), "PSO": ("Pasto", 3),
    "VVC": ("Villavicencio", 3), "RCH": ("Riohacha", 3),
}


def test_full_colombia_coverage() -> None:
    # Registry matches the expected 15 cities exactly (codes + tiers).
    registry = {c.code: (c.name, c.tier) for c in CITY_REGISTRY}
    _check("registry has exactly 15 cities", len(CITY_REGISTRY) == 15)
    _check("registry matches expected city/code/tier set",
           registry == EXPECTED_CITIES)
    # Original three are still present (regression guard).
    for code in ("MDE", "CTG", "SMR"):
        _check(f"{code} still supported", code in registry)

    # Every listed city renders a full Delta appendix with all 4 types.
    for code, (city, tier) in EXPECTED_CITIES.items():
        block = render_delta_lodging_appendix(code, now=NOW)
        _check(f"{code} ({city}, T{tier}): appendix renders", bool(block))
        _check(f"{code}: names {city}", city in block)
        _check(f"{code}: mock labelled", "mock estimates" in block.lower()
               and "not live pricing" in block.lower())
        for at in ACCOMMODATION_ORDER:
            _check(f"{code}: shows {at.label}", at.label in block)
        _check(f"{code}: nightly/weekly/monthly present",
               all(h in block for h in ("Nightly", "Weekly", "Monthly")))


def test_standalone_summary_renders() -> None:
    text = render_all_cities(now=NOW)
    for city in SUPPORTED_CITIES:
        _check(f"standalone summary includes {city}", city in text)
    _check("standalone summary labelled Phase 6A / mock", "Phase 6A" in text)


def main() -> None:
    for fn in (
        test_all_cities_all_types,
        test_length_of_stay_discounts,
        test_value_ranking,
        test_delta_appendix_supported_and_unsupported,
        test_full_colombia_coverage,
        test_future_providers_inert,
        test_standalone_summary_renders,
    ):
        print(f"\n[{fn.__name__}]")
        fn()
    print("\nALL LODGING LAYER TESTS PASSED")


if __name__ == "__main__":
    main()
