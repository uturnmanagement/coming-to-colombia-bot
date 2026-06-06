"""Mock lodging provider (Phase 6A).

Deterministic, offline nightly price bands (USD/night) for the three
Colombia desk destination cities across the four accommodation tiers.
Figures are realistic-but-illustrative budget ranges; they are NOT live
pricing and every quote carries `is_mock=True`.

No network, no randomness — same city always yields the same bands, so
reports and tests are reproducible.
"""
from __future__ import annotations

from lodging.lodging_models import AccommodationType, NightlyQuote
from lodging.providers.base import LodgingProvider, ProviderResult, ProviderStatus

_AT = AccommodationType

# city -> accommodation type -> (low_usd, high_usd) nightly band.
# Phase 6A.1: full Colombia pilot coverage (15 cities). Bands are
# illustrative budget ranges, NOT live pricing — every quote carries
# is_mock=True. Cities are grouped by pilot tier; within each city the
# dorm bed is always the cheapest tier so value ranking is well-defined.
_MOCK_NIGHTLY: dict[str, dict[AccommodationType, tuple[float, float]]] = {
    # --- Tier 1 — primary destinations ---
    "Bogotá": {
        _AT.HOSTEL_DORM: (12.0, 18.0),
        _AT.HOSTEL_PRIVATE_ROOM: (30.0, 46.0),
        _AT.BUDGET_HOTEL: (45.0, 65.0),
        _AT.AIRBNB: (50.0, 78.0),
    },
    "Medellín": {
        _AT.HOSTEL_DORM: (11.0, 16.0),
        _AT.HOSTEL_PRIVATE_ROOM: (28.0, 42.0),
        _AT.BUDGET_HOTEL: (40.0, 58.0),
        _AT.AIRBNB: (45.0, 70.0),
    },
    "Cartagena": {
        _AT.HOSTEL_DORM: (15.0, 22.0),
        _AT.HOSTEL_PRIVATE_ROOM: (38.0, 55.0),
        _AT.BUDGET_HOTEL: (60.0, 85.0),
        _AT.AIRBNB: (65.0, 100.0),
    },
    "Cali": {
        _AT.HOSTEL_DORM: (10.0, 15.0),
        _AT.HOSTEL_PRIVATE_ROOM: (26.0, 40.0),
        _AT.BUDGET_HOTEL: (38.0, 55.0),
        _AT.AIRBNB: (42.0, 65.0),
    },
    "Barranquilla": {
        _AT.HOSTEL_DORM: (11.0, 16.0),
        _AT.HOSTEL_PRIVATE_ROOM: (27.0, 40.0),
        _AT.BUDGET_HOTEL: (40.0, 56.0),
        _AT.AIRBNB: (45.0, 68.0),
    },
    "Santa Marta": {
        _AT.HOSTEL_DORM: (10.0, 15.0),
        _AT.HOSTEL_PRIVATE_ROOM: (24.0, 36.0),
        _AT.BUDGET_HOTEL: (35.0, 50.0),
        _AT.AIRBNB: (40.0, 62.0),
    },
    # --- Tier 2 — secondary cities (coffee region + Bucaramanga) ---
    "Bucaramanga": {
        _AT.HOSTEL_DORM: (9.0, 14.0),
        _AT.HOSTEL_PRIVATE_ROOM: (24.0, 36.0),
        _AT.BUDGET_HOTEL: (36.0, 52.0),
        _AT.AIRBNB: (40.0, 60.0),
    },
    "Pereira": {
        _AT.HOSTEL_DORM: (9.0, 14.0),
        _AT.HOSTEL_PRIVATE_ROOM: (23.0, 35.0),
        _AT.BUDGET_HOTEL: (35.0, 50.0),
        _AT.AIRBNB: (38.0, 58.0),
    },
    "Armenia": {
        _AT.HOSTEL_DORM: (9.0, 13.0),
        _AT.HOSTEL_PRIVATE_ROOM: (22.0, 34.0),
        _AT.BUDGET_HOTEL: (34.0, 48.0),
        _AT.AIRBNB: (37.0, 55.0),
    },
    "Manizales": {
        _AT.HOSTEL_DORM: (9.0, 14.0),
        _AT.HOSTEL_PRIVATE_ROOM: (22.0, 34.0),
        _AT.BUDGET_HOTEL: (34.0, 49.0),
        _AT.AIRBNB: (38.0, 56.0),
    },
    # --- Tier 3 — emerging / regional cities ---
    "Cúcuta": {
        _AT.HOSTEL_DORM: (8.0, 12.0),
        _AT.HOSTEL_PRIVATE_ROOM: (20.0, 30.0),
        _AT.BUDGET_HOTEL: (30.0, 44.0),
        _AT.AIRBNB: (33.0, 50.0),
    },
    "Montería": {
        _AT.HOSTEL_DORM: (8.0, 12.0),
        _AT.HOSTEL_PRIVATE_ROOM: (20.0, 31.0),
        _AT.BUDGET_HOTEL: (31.0, 45.0),
        _AT.AIRBNB: (34.0, 52.0),
    },
    "Pasto": {
        _AT.HOSTEL_DORM: (8.0, 12.0),
        _AT.HOSTEL_PRIVATE_ROOM: (19.0, 29.0),
        _AT.BUDGET_HOTEL: (29.0, 43.0),
        _AT.AIRBNB: (32.0, 49.0),
    },
    "Villavicencio": {
        _AT.HOSTEL_DORM: (9.0, 13.0),
        _AT.HOSTEL_PRIVATE_ROOM: (21.0, 32.0),
        _AT.BUDGET_HOTEL: (32.0, 46.0),
        _AT.AIRBNB: (35.0, 53.0),
    },
    "Riohacha": {
        _AT.HOSTEL_DORM: (10.0, 15.0),
        _AT.HOSTEL_PRIVATE_ROOM: (24.0, 36.0),
        _AT.BUDGET_HOTEL: (35.0, 51.0),
        _AT.AIRBNB: (40.0, 60.0),
    },
}


class MockLodgingProvider(LodgingProvider):
    """Offline deterministic provider used for all Phase 6A estimates."""

    name = "mock_v1"
    is_live = False

    def fetch_city(self, city: str) -> ProviderResult:
        table = _MOCK_NIGHTLY.get(city)
        if table is None:
            return ProviderResult(
                status=ProviderStatus.EMPTY,
                reason=f"no mock data for city {city!r}",
                source=self.name,
            )
        quotes = tuple(
            NightlyQuote(
                city=city,
                accommodation=accommodation,
                low_usd=low,
                high_usd=high,
                source=self.name,
                is_mock=True,
            )
            for accommodation, (low, high) in table.items()
        )
        return ProviderResult(
            status=ProviderStatus.OK, quotes=quotes, source=self.name
        )
