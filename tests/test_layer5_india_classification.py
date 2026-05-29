"""Layer 5 — accommodation classification + provider tests.

Covers:
    - AccommodationCategory enum carries the four spec'd categories
    - MockHostelProvider returns deterministic options per city
    - Provider returns empty tuple for unknown city
    - Provider yields options across all four categories where seeded
    - Provider data passes HostelOption invariants

Runnable directly:
    python tests/test_layer5_india_classification.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.india import (
    AccommodationCategory,
    HostelOption,
    MockHostelProvider,
)
from agents.india.providers import HostelProvider


T0 = datetime(2026, 5, 28, 12, 0, 0)


# ---------- category enum ----------

def test_categories_match_spec_set():
    spec = {
        AccommodationCategory.HOSTEL_DORM,
        AccommodationCategory.HOSTEL_PRIVATE_ROOM,
        AccommodationCategory.BUDGET_HOTEL,
        AccommodationCategory.GUEST_HOUSE,
    }
    assert set(AccommodationCategory) == spec


def test_category_values_are_stable_strings():
    assert AccommodationCategory.HOSTEL_DORM.value == "hostel_dorm"
    assert AccommodationCategory.HOSTEL_PRIVATE_ROOM.value == "hostel_private_room"
    assert AccommodationCategory.BUDGET_HOTEL.value == "budget_hotel"
    assert AccommodationCategory.GUEST_HOUSE.value == "guest_house"


# ---------- provider protocol ----------

def test_mock_provider_satisfies_protocol():
    assert isinstance(MockHostelProvider(), HostelProvider)


def test_mock_provider_known_city_returns_options():
    out = MockHostelProvider().fetch(city="BOG", now=T0)
    assert len(out) == 4
    assert all(isinstance(o, HostelOption) for o in out)


def test_mock_provider_returns_empty_for_unknown_city():
    out = MockHostelProvider().fetch(city="ZZZ", now=T0)
    assert out == ()


def test_mock_provider_case_insensitive_city():
    upper = MockHostelProvider().fetch(city="BOG", now=T0)
    mixed = MockHostelProvider().fetch(city="bog", now=T0)
    assert len(upper) == len(mixed)


def test_mock_provider_deterministic():
    """Two calls back to back must return identical option tuples."""
    a = MockHostelProvider().fetch(city="BOG", now=T0)
    b = MockHostelProvider().fetch(city="BOG", now=T0)
    assert a == b


# ---------- per-category coverage ----------

def test_bog_seeds_all_four_categories():
    out = MockHostelProvider().fetch(city="BOG", now=T0)
    categories = {o.category for o in out}
    assert categories == {
        AccommodationCategory.HOSTEL_DORM,
        AccommodationCategory.HOSTEL_PRIVATE_ROOM,
        AccommodationCategory.BUDGET_HOTEL,
        AccommodationCategory.GUEST_HOUSE,
    }


def test_options_carry_required_fields():
    out = MockHostelProvider().fetch(city="MDE", now=T0)
    for opt in out:
        assert opt.city == "MDE"
        assert opt.name
        assert opt.neighborhood
        assert opt.price_usd > 0
        assert opt.distance_to_center_km >= 0
        assert opt.source == "mock_hostel"
        assert opt.score_breakdown is None    # provider does not score


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
    print(f"\nLayer 5 India classification: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
