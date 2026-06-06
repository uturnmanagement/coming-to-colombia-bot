"""Lodging Intelligence — data models (Phase 6A).

Pure dataclasses, no I/O. These describe estimated accommodation costs
attached to an airfare opportunity for the Colombia desk's 15 supported
destination cities (the full Colombia registry — see CITY_REGISTRY).

Honesty rule (mirrors the Delta renderer): every estimate produced in
Phase 6A is MOCK data. The `is_mock` flag travels with every quote and
summary so no downstream renderer can present these as live pricing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

@dataclass(frozen=True)
class CityProfile:
    """A supported Colombia lodging city: airport code, name, pilot tier."""

    code: str
    name: str
    tier: int


# Canonical registry of supported Colombia lodging cities (Phase 6A.1 —
# full Colombia pilot coverage). This is the SINGLE source of truth:
# code→city mapping, the supported-city list, and tiers all derive from
# it, so they cannot drift apart. City spellings match configs/*.yaml
# (accents preserved: Bogotá, Medellín, Cúcuta, Montería).
CITY_REGISTRY: tuple[CityProfile, ...] = (
    # Tier 1 — primary destinations.
    CityProfile("BOG", "Bogotá", 1),
    CityProfile("MDE", "Medellín", 1),
    CityProfile("CTG", "Cartagena", 1),
    CityProfile("CLO", "Cali", 1),
    CityProfile("BAQ", "Barranquilla", 1),
    CityProfile("SMR", "Santa Marta", 1),
    # Tier 2 — secondary cities (coffee region + Bucaramanga).
    CityProfile("BGA", "Bucaramanga", 2),
    CityProfile("PEI", "Pereira", 2),
    CityProfile("AXM", "Armenia", 2),
    CityProfile("MZL", "Manizales", 2),
    # Tier 3 — emerging / regional cities.
    CityProfile("CUC", "Cúcuta", 3),
    CityProfile("MTR", "Montería", 3),
    CityProfile("PSO", "Pasto", 3),
    CityProfile("VVC", "Villavicencio", 3),
    CityProfile("RCH", "Riohacha", 3),
)

# Derived lookups — keep these in sync by deriving, never hand-listing.
CODE_TO_CITY: dict[str, str] = {c.code: c.name for c in CITY_REGISTRY}
CITY_TO_TIER: dict[str, int] = {c.name: c.tier for c in CITY_REGISTRY}
SUPPORTED_CITIES: tuple[str, ...] = tuple(c.name for c in CITY_REGISTRY)


class AccommodationType(str, Enum):
    """The four accommodation tiers Phase 6 estimates.

    Aligns with India's AccommodationCategory (hostel_dorm,
    hostel_private_room, budget_hotel) but swaps GUEST_HOUSE for AIRBNB,
    which is the fourth tier the Phase 6 mission specifies.
    """

    HOSTEL_DORM = "hostel_dorm"
    HOSTEL_PRIVATE_ROOM = "hostel_private_room"
    BUDGET_HOTEL = "budget_hotel"
    AIRBNB = "airbnb"

    @property
    def label(self) -> str:
        return {
            "hostel_dorm": "Hostel dorm bed",
            "hostel_private_room": "Hostel private room",
            "budget_hotel": "Budget hotel",
            "airbnb": "Airbnb",
        }[self.value]


# Canonical display order for reports (cheap → comfortable).
ACCOMMODATION_ORDER: tuple[AccommodationType, ...] = (
    AccommodationType.HOSTEL_DORM,
    AccommodationType.HOSTEL_PRIVATE_ROOM,
    AccommodationType.BUDGET_HOTEL,
    AccommodationType.AIRBNB,
)


@dataclass(frozen=True)
class NightlyQuote:
    """One provider's nightly price band for a city + accommodation type."""

    city: str
    accommodation: AccommodationType
    low_usd: float
    high_usd: float
    source: str                 # provider name (e.g. "mock_v1")
    is_mock: bool = True

    @property
    def mid_usd(self) -> float:
        return round((self.low_usd + self.high_usd) / 2.0, 2)


@dataclass(frozen=True)
class StayEstimate:
    """Estimated cost for a length of stay, derived from a nightly band.

    `discount_pct` is the length-of-stay discount already baked into the
    low/high figures (0.0 for a single night).
    """

    nights: int
    low_usd: float
    high_usd: float
    discount_pct: float

    @property
    def mid_usd(self) -> float:
        return round((self.low_usd + self.high_usd) / 2.0, 2)


@dataclass(frozen=True)
class LodgingEstimate:
    """Full estimate for one accommodation type in one city.

    Carries the nightly band plus the derived weekly (7-night) and
    monthly (30-night) projections. `value_rank` is filled by the ranker
    (1 = best value).
    """

    city: str
    accommodation: AccommodationType
    nightly: StayEstimate       # nights == 1
    weekly: StayEstimate        # nights == 7
    monthly: StayEstimate       # nights == 30
    source: str
    is_mock: bool
    value_rank: Optional[int] = None

    @property
    def is_best_value(self) -> bool:
        return self.value_rank == 1


@dataclass(frozen=True)
class CityLodgingSummary:
    """Ranked lodging estimates for one city, ready to render."""

    city: str
    generated_at: datetime
    estimates: tuple[LodgingEstimate, ...]   # ranked best-value first
    is_mock: bool
    provider_note: str

    @property
    def best_value(self) -> Optional[LodgingEstimate]:
        return self.estimates[0] if self.estimates else None
