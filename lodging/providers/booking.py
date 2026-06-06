"""Booking.com provider — STUB (reserved for a future phase).

Architecture placeholder so the engine can enumerate future live
sources. Phase 6A wires NO network: `fetch_city` returns STUB until a
later phase supplies credentials and a real transport. `is_live` stays
False so the engine never selects it over the mock provider.
"""
from __future__ import annotations

from lodging.providers.base import LodgingProvider, ProviderResult, ProviderStatus


class BookingComProvider(LodgingProvider):
    name = "booking_com"
    is_live = False

    def fetch_city(self, city: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderStatus.STUB,
            reason="Booking.com live wiring reserved for a later phase "
            "(Phase 6A performs no network I/O)",
            source=self.name,
        )
