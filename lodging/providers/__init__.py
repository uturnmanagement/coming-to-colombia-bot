"""Lodging providers.

Phase 6A: `MockLodgingProvider` is the only usable source. The live
providers (Booking.com, Hostelworld, Airbnb) are present as STUBs so the
architecture is ready for a later phase to wire real transports.
"""
from __future__ import annotations

from lodging.providers.airbnb import AirbnbProvider
from lodging.providers.base import (
    LodgingProvider,
    ProviderResult,
    ProviderStatus,
)
from lodging.providers.booking import BookingComProvider
from lodging.providers.hostelworld import HostelworldProvider
from lodging.providers.mock import MockLodgingProvider

# Future live sources, in the order a later phase would consult them.
# Present for architecture/enumeration only — all are STUBs in Phase 6A.
FUTURE_LIVE_PROVIDERS: tuple[type[LodgingProvider], ...] = (
    BookingComProvider,
    HostelworldProvider,
    AirbnbProvider,
)

__all__ = [
    "LodgingProvider",
    "ProviderResult",
    "ProviderStatus",
    "MockLodgingProvider",
    "BookingComProvider",
    "HostelworldProvider",
    "AirbnbProvider",
    "FUTURE_LIVE_PROVIDERS",
]
