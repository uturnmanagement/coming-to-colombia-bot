"""Value ranking (Phase 6A).

Ranks a city's accommodation estimates best-value-first. "Value" here is
simply the lowest mid nightly price — the cheapest usable bed wins —
with accommodation display order as a stable tiebreaker so equal prices
rank deterministically. Returns NEW estimates with `value_rank` filled
(1 = best value); inputs are frozen and left untouched.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from lodging.lodging_models import ACCOMMODATION_ORDER, LodgingEstimate

_ORDER_INDEX = {a: i for i, a in enumerate(ACCOMMODATION_ORDER)}


def rank_estimates(
    estimates: Iterable[LodgingEstimate],
) -> tuple[LodgingEstimate, ...]:
    """Return estimates sorted best-value-first with `value_rank` set."""
    ordered = sorted(
        estimates,
        key=lambda e: (e.nightly.mid_usd, _ORDER_INDEX.get(e.accommodation, 99)),
    )
    return tuple(
        replace(est, value_rank=i) for i, est in enumerate(ordered, start=1)
    )
