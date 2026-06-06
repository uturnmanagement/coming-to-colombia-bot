"""Lodging Intelligence Layer (Phase 6A).

Attaches estimated lodging intelligence — hostel dorm beds, private
hostel rooms, budget hotels, and Airbnb — to airfare opportunities for
the Colombia desk's 15 supported destination cities (the full Colombia
registry across tiers 1–3 — see lodging_models.CITY_REGISTRY).

Phase 6A uses MOCK pricing only (no live API calls). The provider
architecture is ready for future live sources (Booking.com, Hostelworld,
Airbnb), which ship as STUBs until a later phase wires real transports.

Public surface:
    LodgingEngine                       — orchestrates a city summary
    render_delta_lodging_appendix(code) — block appended to Delta reports
    render_all_cities()                 — standalone Lodging Summary
"""
from __future__ import annotations

from lodging.lodging_engine import CODE_TO_CITY, LodgingEngine, city_for_code
from lodging.lodging_models import (
    ACCOMMODATION_ORDER,
    AccommodationType,
    CityLodgingSummary,
    CITY_REGISTRY,
    CITY_TO_TIER,
    CityProfile,
    LodgingEstimate,
    NightlyQuote,
    StayEstimate,
    SUPPORTED_CITIES,
)
from lodging.lodging_report import (
    render_all_cities,
    render_delta_lodging_appendix,
)

__all__ = [
    "LodgingEngine",
    "city_for_code",
    "CODE_TO_CITY",
    "CITY_REGISTRY",
    "CITY_TO_TIER",
    "CityProfile",
    "AccommodationType",
    "ACCOMMODATION_ORDER",
    "SUPPORTED_CITIES",
    "NightlyQuote",
    "StayEstimate",
    "LodgingEstimate",
    "CityLodgingSummary",
    "render_delta_lodging_appendix",
    "render_all_cities",
]
