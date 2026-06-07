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


def discount_for_nights(accommodation: AccommodationType, nights: int) -> float:
    """Length-of-stay discount for an arbitrary night count.

    Piecewise-linear between the known anchors: 0% at 1 night, the weekly
    discount at 7 nights, the monthly discount at 30 nights, capped at the
    monthly discount beyond 30. Continuous and never extrapolates past the
    monthly rate — a conservative reading of the same per-type discounts the
    nightly/weekly/monthly projections use.
    """
    weekly_disc, monthly_disc = _DISCOUNTS.get(accommodation, (0.0, 0.0))
    n = max(1, int(nights))
    if n <= 1:
        return 0.0
    if n <= WEEKLY_NIGHTS:
        return weekly_disc * (n - 1) / (WEEKLY_NIGHTS - 1)
    if n <= MONTHLY_NIGHTS:
        frac = (n - WEEKLY_NIGHTS) / (MONTHLY_NIGHTS - WEEKLY_NIGHTS)
        return weekly_disc + (monthly_disc - weekly_disc) * frac
    return monthly_disc


def stay_for_nights(estimate: LodgingEstimate, nights: int) -> StayEstimate:
    """Price an arbitrary-length stay from an estimate's nightly band.

    Pure math over the existing per-night low/high band — no new provider
    call — so the result inherits the estimate's MOCK/LIVE provenance.
    """
    n = max(1, int(nights))
    disc = discount_for_nights(estimate.accommodation, n)
    factor = n * (1.0 - disc)
    return StayEstimate(
        nights=n,
        low_usd=round(estimate.nightly.low_usd * factor, 2),
        high_usd=round(estimate.nightly.high_usd * factor, 2),
        discount_pct=round(disc, 4),
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
