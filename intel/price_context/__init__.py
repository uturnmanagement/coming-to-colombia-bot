"""Price-context intel — classify an observed fare against a band.

Pure-logic. Echo wraps this in a specialist shell. Real history-driven
percentile work arrives when the lodging hook + a price-history store
arrive in Layer 4+.
"""
from .classifier import (
    PriceBand,
    PricePosition,
    classify_price_position,
)

__all__ = ["PriceBand", "PricePosition", "classify_price_position"]
