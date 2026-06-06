"""Length-of-stay pricing (Phase 6A).

Turns a single nightly price band into nightly / weekly (7-night) /
monthly (30-night) estimates, applying a per-accommodation-type
length-of-stay discount. Pure math, no I/O.

Discounts reflect real-world norms: longer stays cost less per night,
and Airbnb monthly discounts are typically the steepest while hostel
dorm beds discount the least.
"""
from __future__ import annotations

from lodging.lodging_models import (
    AccommodationType,
    LodgingEstimate,
    NightlyQuote,
    StayEstimate,
)

WEEKLY_NIGHTS = 7
MONTHLY_NIGHTS = 30

# accommodation type -> (weekly_discount, monthly_discount) as fractions.
_DISCOUNTS: dict[AccommodationType, tuple[float, float]] = {
    AccommodationType.HOSTEL_DORM: (0.05, 0.20),
    AccommodationType.HOSTEL_PRIVATE_ROOM: (0.08, 0.25),
    AccommodationType.BUDGET_HOTEL: (0.10, 0.30),
    AccommodationType.AIRBNB: (0.15, 0.40),
}


def _stay(nightly_low: float, nightly_high: float, nights: int,
          discount: float) -> StayEstimate:
    factor = nights * (1.0 - discount)
    return StayEstimate(
        nights=nights,
        low_usd=round(nightly_low * factor, 2),
        high_usd=round(nightly_high * factor, 2),
        discount_pct=discount,
    )


def estimate_from_quote(quote: NightlyQuote) -> LodgingEstimate:
    """Project a nightly band into nightly/weekly/monthly estimates."""
    weekly_disc, monthly_disc = _DISCOUNTS.get(
        quote.accommodation, (0.0, 0.0)
    )
    nightly = StayEstimate(
        nights=1,
        low_usd=round(quote.low_usd, 2),
        high_usd=round(quote.high_usd, 2),
        discount_pct=0.0,
    )
    weekly = _stay(quote.low_usd, quote.high_usd, WEEKLY_NIGHTS, weekly_disc)
    monthly = _stay(quote.low_usd, quote.high_usd, MONTHLY_NIGHTS, monthly_disc)
    return LodgingEstimate(
        city=quote.city,
        accommodation=quote.accommodation,
        nightly=nightly,
        weekly=weekly,
        monthly=monthly,
        source=quote.source,
        is_mock=quote.is_mock,
    )
