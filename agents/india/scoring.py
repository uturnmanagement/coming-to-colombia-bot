"""India's scoring engine.

Each accommodation option earns four sub-scores (0..100, higher is
better) plus a weighted overall:

    price          favors observed << typical for the category
    location       favors distance_to_center_km close to 0
    season         derived from Layer 4 Season (LOW best, PEAK worst)
    lodging_signal derived from Layer 4 LodgingColor (RED best)

All inputs are pure values; the engine never reads I/O.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from agents.logging_setup import get_logger
from intel.lodging.scoring import LodgingColor
from intel.lodging.seasons import Season

from .report import AccommodationCategory

log = get_logger("india")


# Per-category typical USD/night used as the price-score anchor.
# Numbers are conservative Colombia-Desk defaults; the operator can
# override by constructing India with a different table.
TYPICAL_PRICE_USD_BY_CATEGORY: dict[AccommodationCategory, float] = {
    AccommodationCategory.HOSTEL_DORM: 15.0,
    AccommodationCategory.HOSTEL_PRIVATE_ROOM: 35.0,
    AccommodationCategory.BUDGET_HOTEL: 50.0,
    AccommodationCategory.GUEST_HOUSE: 40.0,
}


# Env knob (Layer 6 / O3): a path to a JSON object mapping
# AccommodationCategory.value -> typical USD/night, e.g.
#   {"hostel_dorm": 18, "budget_hotel": 55}
# Keys not recognized are ignored; a missing/unreadable/invalid file
# degrades quietly to None so the module defaults stay in force.
TYPICAL_PRICES_ENV_VAR = "INDIA_TYPICAL_PRICES_JSON"


def load_category_typicals_from_env(
    env: Optional[dict] = None,
) -> Optional[dict[AccommodationCategory, float]]:
    """Best-effort load of a per-category typical-price table from the
    JSON file named by ``INDIA_TYPICAL_PRICES_JSON``.

    Returns None when the env var is unset OR the file is missing /
    unreadable / malformed — callers then fall back to
    ``TYPICAL_PRICE_USD_BY_CATEGORY``. Never raises.
    """
    source = (env if env is not None else os.environ).get(TYPICAL_PRICES_ENV_VAR)
    if not source:
        return None
    try:
        with open(source, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:  # noqa: BLE001 — config absence is not an error
        log.warning("could not read %s=%s; using default typicals",
                    TYPICAL_PRICES_ENV_VAR, source)
        return None
    if not isinstance(raw, dict):
        log.warning("%s did not contain a JSON object; ignoring", source)
        return None
    by_value = {c.value: c for c in AccommodationCategory}
    table: dict[AccommodationCategory, float] = {}
    for key, val in raw.items():
        cat = by_value.get(str(key).lower())
        if cat is None:
            continue
        try:
            price = float(val)
        except (TypeError, ValueError):
            continue
        if price > 0:
            table[cat] = price
    return table or None

# Score weights — must sum to 1.0. Adjust together if rebalancing.
SCORE_WEIGHTS: dict[str, float] = {
    "price": 0.40,
    "location": 0.20,
    "season": 0.15,
    "lodging_signal": 0.25,
}


@dataclass(frozen=True)
class ScoreBreakdown:
    price: float
    location: float
    season: float
    lodging_signal: float
    overall: float


# --- per-axis scorers ----------------------------------------------------

def score_price(
    observed_usd: float,
    category: AccommodationCategory,
    *,
    typical_table: Optional[dict[AccommodationCategory, float]] = None,
) -> float:
    """Linear from 100 at observed <= 0.7*typical to 0 at observed >= 1.3*typical.

    Anything outside [0.7, 1.3] is clamped.
    """
    if observed_usd < 0:
        raise ValueError(f"observed_usd must be >= 0, got {observed_usd}")
    table = typical_table or TYPICAL_PRICE_USD_BY_CATEGORY
    typical = table.get(category)
    if typical is None or typical <= 0:
        return 50.0  # neutral — no anchor available
    ratio = observed_usd / typical
    if ratio <= 0.70:
        return 100.0
    if ratio >= 1.30:
        return 0.0
    # 0.70 -> 100, 1.30 -> 0  ⇒ slope = -100 / 0.60
    return round((1.30 - ratio) / 0.60 * 100.0, 4)


def score_location(distance_to_center_km: float) -> float:
    """100 at the center, 0 at 5+ km away."""
    if distance_to_center_km < 0:
        raise ValueError(
            f"distance_to_center_km must be >= 0, got {distance_to_center_km}"
        )
    if distance_to_center_km >= 5.0:
        return 0.0
    return round((1.0 - distance_to_center_km / 5.0) * 100.0, 4)


def score_season(season: Optional[Season]) -> float:
    """Travel-window bias.

    LOW season scores best — that is when Colombia hostels see the
    most budget travelers and the deepest deals; PEAK and HIGH
    discount the option because demand is up. None (no season known)
    is neutral.
    """
    if season is None:
        return 50.0
    return {
        Season.LOW: 100.0,
        Season.MID: 75.0,
        Season.HIGH: 60.0,
        Season.PEAK: 40.0,
    }[season]


def score_lodging_signal(color: Optional[LodgingColor]) -> float:
    """City-wide lodging context from Layer 4.

    RED means observed lodging prices are 15%+ below typical
    city-wide — favorable for budget travelers. None means the brain
    has no opinion yet (no baseline, intel disabled, etc.) and gets
    a neutral 50.
    """
    if color is None:
        return 50.0
    return {
        LodgingColor.RED: 100.0,
        LodgingColor.YELLOW: 75.0,
        LodgingColor.GREEN: 50.0,
    }[color]


# --- overall -------------------------------------------------------------

def score_option(
    *,
    observed_usd: float,
    category: AccommodationCategory,
    distance_to_center_km: float,
    season: Optional[Season] = None,
    lodging_color: Optional[LodgingColor] = None,
    typical_table: Optional[dict[AccommodationCategory, float]] = None,
) -> ScoreBreakdown:
    """Score one HostelOption candidate end-to-end."""
    price = score_price(observed_usd, category, typical_table=typical_table)
    location = score_location(distance_to_center_km)
    season_score = score_season(season)
    lodging_score = score_lodging_signal(lodging_color)
    overall = round(
        SCORE_WEIGHTS["price"] * price
        + SCORE_WEIGHTS["location"] * location
        + SCORE_WEIGHTS["season"] * season_score
        + SCORE_WEIGHTS["lodging_signal"] * lodging_score,
        4,
    )
    return ScoreBreakdown(
        price=price,
        location=location,
        season=season_score,
        lodging_signal=lodging_score,
        overall=overall,
    )
