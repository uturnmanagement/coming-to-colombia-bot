"""Lodging Intelligence engine (Phase 6A).

Orchestrates: provider → nightly quotes → length-of-stay pricing →
value ranking → CityLodgingSummary. Phase 6A always uses the offline
MockLodgingProvider; the live providers exist as STUBs and the engine
records which future sources are reserved (never selecting them while
`is_live` is False).

No network, no flight/return/heartbeat/Telegram logic is touched here —
this is a self-contained intelligence layer that other reports consume.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lodging.lodging_models import (
    CityLodgingSummary,
    CODE_TO_CITY,
    SUPPORTED_CITIES,
)
from lodging.pricing.estimator import estimate_from_quote
from lodging.providers import FUTURE_LIVE_PROVIDERS, MockLodgingProvider
from lodging.providers.base import LodgingProvider, ProviderStatus
from lodging.ranking.ranker import rank_estimates

# Destination airport code -> city name now lives in the canonical
# CITY_REGISTRY (lodging_models.CODE_TO_CITY), re-exported here for
# backward compatibility with callers that import it from the engine.


def city_for_code(code: Optional[str]) -> Optional[str]:
    """Resolve a destination airport code to a supported city, or None."""
    if not code:
        return None
    return CODE_TO_CITY.get(str(code).upper())


class LodgingEngine:
    """Produces lodging summaries for the desk's destination cities."""

    def __init__(self, provider: Optional[LodgingProvider] = None) -> None:
        # Phase 6A: mock only. A later phase passes a live provider here.
        self.provider: LodgingProvider = provider or MockLodgingProvider()

    def _provider_note(self) -> str:
        future = ", ".join(p.name for p in FUTURE_LIVE_PROVIDERS)
        return (
            f"source: {self.provider.name} "
            f"(live={'yes' if self.provider.is_live else 'no'}) · "
            f"future live providers reserved: {future}"
        )

    def summarize_city(
        self, city: str, *, now: Optional[datetime] = None
    ) -> CityLodgingSummary:
        """Build a ranked lodging summary for one city.

        Always returns a summary; an unknown city or non-OK provider
        yields an empty (but well-formed) summary rather than raising.
        """
        when = now or datetime.now()
        result = self.provider.fetch_city(city)
        if result.status is not ProviderStatus.OK or not result.quotes:
            return CityLodgingSummary(
                city=city,
                generated_at=when,
                estimates=(),
                is_mock=not self.provider.is_live,
                provider_note=(
                    f"{self._provider_note()} · "
                    f"no estimates ({result.status.value}"
                    f"{': ' + result.reason if result.reason else ''})"
                ),
            )

        estimates = [estimate_from_quote(q) for q in result.quotes]
        ranked = rank_estimates(estimates)
        return CityLodgingSummary(
            city=city,
            generated_at=when,
            estimates=ranked,
            is_mock=not self.provider.is_live,
            provider_note=self._provider_note(),
        )

    def summarize_for_code(
        self, code: Optional[str], *, now: Optional[datetime] = None
    ) -> Optional[CityLodgingSummary]:
        """Summarize lodging for a destination airport code.

        Returns None when the code is not one of the supported desk
        cities, so a caller can cleanly skip the lodging appendix.
        """
        city = city_for_code(code)
        if city is None:
            return None
        return self.summarize_city(city, now=now)

    def summarize_all(
        self, *, now: Optional[datetime] = None
    ) -> tuple[CityLodgingSummary, ...]:
        """Summarize every supported city (used for standalone reports)."""
        return tuple(self.summarize_city(c, now=now) for c in SUPPORTED_CITIES)
