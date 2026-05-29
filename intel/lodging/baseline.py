"""Baseline aggregation — pure logic.

`compute_baseline(observations, lookback_days, now)` takes a sequence
of LodgingObservation and produces a LodgingBaseline. It rejects
observations outside the lookback window and uses the median (robust
against outlier scrape data). Returns None on an empty effective set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, Optional

from .providers.interface import LodgingObservation


@dataclass(frozen=True)
class LodgingBaseline:
    city: str
    neighborhood: Optional[str]
    beds: Optional[int]
    baseline_price_usd: float
    sample_size: int
    lookback_days: int
    computed_at: datetime
    source_set: tuple[str, ...] = field(default_factory=tuple)


def compute_baseline(
    observations: Iterable[LodgingObservation],
    *,
    lookback_days: int,
    now: datetime,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    beds: Optional[int] = None,
) -> Optional[LodgingBaseline]:
    """Median price over the lookback window. Pure — no I/O."""
    if lookback_days <= 0:
        raise ValueError(f"lookback_days must be > 0, got {lookback_days}")
    cutoff = now - timedelta(days=lookback_days)

    in_window: list[LodgingObservation] = []
    for obs in observations:
        if obs.observed_at < cutoff or obs.observed_at > now:
            continue
        if city is not None and obs.city.upper() != city.upper():
            continue
        if neighborhood is not None and obs.neighborhood != neighborhood:
            continue
        if beds is not None and obs.beds != beds:
            continue
        in_window.append(obs)

    if not in_window:
        return None

    prices = [o.price_usd for o in in_window]
    sources = tuple(sorted({o.source for o in in_window}))
    canonical_city = (city or in_window[0].city).upper()
    canonical_neighborhood = neighborhood or in_window[0].neighborhood
    canonical_beds = beds if beds is not None else in_window[0].beds

    return LodgingBaseline(
        city=canonical_city,
        neighborhood=canonical_neighborhood,
        beds=canonical_beds,
        baseline_price_usd=round(median(prices), 2),
        sample_size=len(prices),
        lookback_days=lookback_days,
        computed_at=now,
        source_set=sources,
    )
