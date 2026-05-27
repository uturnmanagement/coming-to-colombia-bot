"""Classify an observed price against a typical-price band.

Layer 3 uses the region pack's `typical_price_usd` as the band anchor.
Real percentile work over a price-history store is reserved for Layer
4+ (alongside the lodging hook), so this module is intentionally tiny
and deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PriceBand:
    typical_usd: float
    great_below_pct: float = 0.70   # ≤ 70% of typical → "great"
    good_below_pct: float = 0.85    # ≤ 85% of typical → "good"
    normal_above_pct: float = 1.10  # >110% of typical → "high"


@dataclass(frozen=True)
class PricePosition:
    label: str                 # "great" | "good" | "normal" | "high"
    percent_of_typical: float  # 0..>1, observed / typical
    band: PriceBand


def classify_price_position(
    observed_usd: float, band: PriceBand
) -> PricePosition:
    """Place an observed price on the band."""
    if band.typical_usd <= 0:
        raise ValueError(f"band.typical_usd must be positive: {band.typical_usd}")
    ratio = observed_usd / band.typical_usd

    if ratio <= band.great_below_pct:
        label = "great"
    elif ratio <= band.good_below_pct:
        label = "good"
    elif ratio <= band.normal_above_pct:
        label = "normal"
    else:
        label = "high"

    return PricePosition(label=label, percent_of_typical=round(ratio, 4), band=band)
