"""Airbnb provider — STUB (reserved for a future phase).

Architecture placeholder; no network in Phase 6A. Returns STUB until a
later phase wires a real transport. `is_live` stays False so the engine
never selects it over the mock provider.
"""
from __future__ import annotations

from lodging.providers.base import LodgingProvider, ProviderResult, ProviderStatus


class AirbnbProvider(LodgingProvider):
    name = "airbnb"
    is_live = False

    def fetch_city(self, city: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderStatus.STUB,
            reason="Airbnb live wiring reserved for a later phase "
            "(Phase 6A performs no network I/O)",
            source=self.name,
        )
