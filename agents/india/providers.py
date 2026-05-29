"""India — accommodation provider abstractions.

Layer 5 ships ONE provider: MockHostelProvider. No HTTP. No scraping.
No third-party APIs. Deterministic synthetic options keyed by city so
every test runs hermetically and every run yields identical data for
the same city.

When live providers (Hostelworld, Booking, Airbnb-budget tier) arrive
in a later layer, they will share a Protocol with this mock — same
`name` + `fetch(city, now)` shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from .report import AccommodationCategory, HostelOption


@runtime_checkable
class HostelProvider(Protocol):
    name: str

    def fetch(
        self, *, city: str, now: Optional[datetime] = None,
    ) -> tuple[HostelOption, ...]:
        ...


# Deterministic per-city seed for synthetic options. Picked to give
# India interesting score variance — different price tiers, different
# locations — without anyone confusing the output for real data.
_MOCK_OPTIONS_BY_CITY: dict[str, tuple[dict, ...]] = {
    "BOG": (
        dict(name="Mock Dorm El Centro", category=AccommodationCategory.HOSTEL_DORM,
             neighborhood="La Candelaria", price_usd=12.0,
             distance_to_center_km=0.4),
        dict(name="Mock Private Chapinero",
             category=AccommodationCategory.HOSTEL_PRIVATE_ROOM,
             neighborhood="Chapinero", price_usd=28.0,
             distance_to_center_km=1.6),
        dict(name="Mock Budget Hotel Usaquen",
             category=AccommodationCategory.BUDGET_HOTEL,
             neighborhood="Usaquén", price_usd=42.0,
             distance_to_center_km=3.2),
        dict(name="Mock Guest House Quinta",
             category=AccommodationCategory.GUEST_HOUSE,
             neighborhood="Quinta Camacho", price_usd=38.0,
             distance_to_center_km=2.4),
    ),
    "MDE": (
        dict(name="Mock Dorm Poblado", category=AccommodationCategory.HOSTEL_DORM,
             neighborhood="El Poblado", price_usd=16.0,
             distance_to_center_km=2.0),
        dict(name="Mock Private Laureles",
             category=AccommodationCategory.HOSTEL_PRIVATE_ROOM,
             neighborhood="Laureles", price_usd=30.0,
             distance_to_center_km=1.0),
        dict(name="Mock Budget Hotel Envigado",
             category=AccommodationCategory.BUDGET_HOTEL,
             neighborhood="Envigado", price_usd=48.0,
             distance_to_center_km=4.5),
    ),
    "CTG": (
        dict(name="Mock Dorm Getsemani",
             category=AccommodationCategory.HOSTEL_DORM,
             neighborhood="Getsemaní", price_usd=18.0,
             distance_to_center_km=0.6),
        dict(name="Mock Private Centro Historico",
             category=AccommodationCategory.HOSTEL_PRIVATE_ROOM,
             neighborhood="Centro Histórico", price_usd=45.0,
             distance_to_center_km=0.2),
        dict(name="Mock Guest House Manga",
             category=AccommodationCategory.GUEST_HOUSE,
             neighborhood="Manga", price_usd=55.0,
             distance_to_center_km=2.1),
    ),
}


@dataclass
class MockHostelProvider(HostelProvider):
    """Deterministic, hermetic. The only provider Layer 5 ships."""
    name: str = "mock_hostel"

    def fetch(
        self, *, city: str, now: Optional[datetime] = None,
    ) -> tuple[HostelOption, ...]:
        seeds = _MOCK_OPTIONS_BY_CITY.get(city.upper(), ())
        out: list[HostelOption] = []
        for idx, seed in enumerate(seeds):
            out.append(HostelOption(
                name=seed["name"],
                category=seed["category"],
                city=city.upper(),
                neighborhood=seed["neighborhood"],
                price_usd=float(seed["price_usd"]),
                distance_to_center_km=float(seed["distance_to_center_km"]),
                source=self.name,
                listing_ref=f"mock-{city.upper()}-{idx}",
            ))
        return tuple(out)
