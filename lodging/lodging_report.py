"""Lodging report — public rendering entry points (Phase 6A).

Thin facade over the engine + summary renderer. Two uses:

1. `render_delta_lodging_appendix(destination_code)` — the block the
   Delta Return Optimizer report appends for a destination city. Returns
   "" for any code outside the supported desk cities (the 15-city
   Colombia registry, lodging_models.CITY_REGISTRY) so the flight
   report degrades cleanly.
2. `render_all_cities()` — a standalone Lodging Summary across all
   supported cities, for demos / manual review.

This module performs NO network I/O and touches no flight, return,
heartbeat, or Telegram logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from lodging.lodging_engine import LodgingEngine
from lodging.pricing.estimator import stay_for_nights
from lodging.reports.summary import render_city_summary

_HEADER = "LODGING INTELLIGENCE APPENDIX (Phase 6A — mock data)"


@dataclass(frozen=True)
class StayWindowEstimate:
    """Best-value lodging priced for a specific stay length (Tier 3).

    Couples lodging to a chosen flight return window: `nights` comes from
    the return optimizer, the cost band is the best-value accommodation
    priced for exactly that many nights. `is_mock` rides through from the
    summary so honesty badges stay accurate; this object carries NO flight
    data (the combined trip total is assembled by the caller).
    """

    city: str
    nights: int
    accommodation_label: str
    low_usd: float
    high_usd: float
    nightly_mid_usd: float
    discount_pct: float
    is_mock: bool

    @property
    def mid_usd(self) -> float:
        return round((self.low_usd + self.high_usd) / 2.0, 2)


def stay_window_estimate(
    destination_code: Optional[str],
    nights: int,
    *,
    now: Optional[datetime] = None,
) -> Optional[StayWindowEstimate]:
    """Price the best-value stay for `nights` at a destination city.

    Returns None when the code is not a supported desk city, there are no
    lodging estimates, or `nights` is not positive — so a caller can cleanly
    skip the coupled-stay block. No flight logic, no network I/O.
    """
    if nights is None or int(nights) <= 0:
        return None
    summary = LodgingEngine().summarize_for_code(destination_code, now=now)
    if summary is None or not summary.estimates:
        return None
    best = summary.best_value
    if best is None:
        return None
    stay = stay_for_nights(best, int(nights))
    return StayWindowEstimate(
        city=summary.city,
        nights=stay.nights,
        accommodation_label=best.accommodation.label,
        low_usd=stay.low_usd,
        high_usd=stay.high_usd,
        nightly_mid_usd=best.nightly.mid_usd,
        discount_pct=stay.discount_pct,
        is_mock=summary.is_mock,
    )


def render_stay_window_block(est: StayWindowEstimate) -> str:
    """Render the coupled-stay block as plain aligned text (no flight data).

    The caller (Oak Street) wraps this in <pre> for Telegram and prepends a
    combined airfare + lodging trip total. Mirrors the summary renderer's
    honesty rule — mock estimates are always labelled.
    """
    badge = "MOCK" if est.is_mock else "LIVE"
    lines = [
        f"STAY FOR YOUR RETURN WINDOW — {est.city} ({est.nights} nights) [{badge}]",
    ]
    if est.is_mock:
        lines.append("mock estimate (Phase 6A) — illustrative, NOT live pricing")
    disc = (
        f", -{est.discount_pct * 100:.0f}% length-of-stay"
        if est.discount_pct > 0 else ""
    )
    lines.append(
        f"Best value: {est.accommodation_label} — "
        f"${est.low_usd:,.0f}–${est.high_usd:,.0f} for {est.nights} nights "
        f"(~${est.nightly_mid_usd:,.0f}/night{disc})"
    )
    return "\n".join(lines)


def render_delta_lodging_appendix(
    destination_code: Optional[str], *, now: Optional[datetime] = None
) -> str:
    """Render the lodging block for a Delta report's destination city.

    Returns an empty string when the destination is not one of the
    supported desk cities (the 15-city Colombia registry — see
    lodging_models.CITY_REGISTRY).
    """
    engine = LodgingEngine()
    summary = engine.summarize_for_code(destination_code, now=now)
    if summary is None or not summary.estimates:
        return ""
    return render_city_summary(summary)


def render_all_cities(*, now: Optional[datetime] = None) -> str:
    """Standalone Lodging Summary across all supported cities (the
    15-city Colombia registry)."""
    engine = LodgingEngine()
    blocks = [_HEADER, ""]
    for summary in engine.summarize_all(now=now):
        blocks.append(render_city_summary(summary).rstrip())
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"
