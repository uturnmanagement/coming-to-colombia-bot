"""Deterministic mock lodging provider — drives every Layer 4 test.

The mock returns N observations for the requested window, priced from
a city-keyed anchor with a small jitter. Numbers are plausible but
fictional — do NOT treat them as real Colombian listings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .interface import (
    LodgingObservation,
    LodgingProvider,
    ProviderResult,
    ProviderStatus,
)


# Deterministic city anchors (USD / night).
_CITY_ANCHORS = {
    "BOG": 55.0,   # Bogotá
    "MDE": 65.0,   # Medellín
    "CTG": 90.0,   # Cartagena
    "CLO": 50.0,   # Cali
    "BAQ": 60.0,   # Barranquilla
    "SMR": 80.0,   # Santa Marta
}


@dataclass
class MockLodgingProvider(LodgingProvider):
    """Returns one observation per stay-night in the lookback window."""
    name: str = "mock"
    seeded_anchor_usd: Optional[float] = None
    jitter_amplitude_usd: float = 8.0
    samples_per_day: int = 1
    # Override to test EMPTY / ERROR paths.
    forced_status: Optional[ProviderStatus] = None
    forced_reason: str = ""
    # Use these observations verbatim instead of synthesizing.
    canned: Optional[tuple[LodgingObservation, ...]] = None

    def fetch(
        self,
        *,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        lookback_days: int = 90,
        now: Optional[datetime] = None,
    ) -> ProviderResult:
        if self.forced_status is not None:
            return ProviderResult(
                status=self.forced_status,
                observations=(),
                reason=self.forced_reason or self.forced_status.value,
                source=self.name,
            )
        if self.canned is not None:
            return ProviderResult(
                status=(ProviderStatus.OK if self.canned else ProviderStatus.EMPTY),
                observations=tuple(self.canned),
                reason="canned",
                source=self.name,
            )

        when = now or datetime(2026, 5, 28, 12, 0, 0)
        anchor = self.seeded_anchor_usd if self.seeded_anchor_usd is not None \
            else _CITY_ANCHORS.get(city.upper(), 70.0)

        observations: list[LodgingObservation] = []
        for offset in range(lookback_days):
            stay_day = (when - timedelta(days=lookback_days - offset)).date()
            for k in range(self.samples_per_day):
                # Cheap deterministic jitter — no random module needed.
                jitter = ((offset * 7 + k * 13) % 11) - 5
                price = round(anchor + jitter * (self.jitter_amplitude_usd / 5.0), 2)
                observations.append(LodgingObservation(
                    city=city.upper(),
                    neighborhood=neighborhood,
                    beds=beds,
                    observed_at=when - timedelta(days=lookback_days - offset),
                    stay_date=stay_day,
                    price_usd=price,
                    source=self.name,
                    listing_ref=f"mock-{city}-{offset}-{k}",
                ))
        return ProviderResult(
            status=ProviderStatus.OK,
            observations=tuple(observations),
            reason=f"{len(observations)} synthetic observations",
            source=self.name,
        )
