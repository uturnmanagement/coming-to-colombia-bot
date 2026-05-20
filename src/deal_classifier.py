"""Classify route comparisons as GREEN / YELLOW / RED deals.

GREEN  - normal/average deal: log only, include in daily summary.
YELLOW - strong deal: send a Telegram alert, recheck periodically.
RED    - rare urgent deal: alert immediately, start heartbeat pings.

A late-night arrival at a destination that carries arrival rules can
never be RED (see arrival_rules) — this generalizes the original
Medellin late-night rule to any destination.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import region
from .arrival_rules import ArrivalCheck, check_arrival
from .route_compare import RouteComparison

# Extra travel time (positioning vs direct) treated as a real penalty.
LONG_DETOUR_HOURS = 10.0


class DealColor(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class DealClassification:
    color: DealColor
    urgency_score: float
    explanation: str
    price_usd: float
    value_savings_usd: float
    positioning_savings_usd: float
    effective_savings_usd: float
    notes: list[str] = field(default_factory=list)

    @property
    def is_alertable(self) -> bool:
        return self.color in (DealColor.YELLOW, DealColor.RED)


@dataclass
class DealResult:
    """Everything the bot knows about one destination after a scan."""

    comparison: RouteComparison
    classification: DealClassification
    arrival: ArrivalCheck

    @property
    def destination(self) -> str:
        return self.comparison.destination

    @property
    def color(self) -> DealColor:
        return self.classification.color


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def classify(
    comparison: RouteComparison, config, arrival: ArrivalCheck
) -> DealClassification:
    """Apply the GREEN/YELLOW/RED rules to one destination comparison."""
    recommended = comparison.recommended
    notes: list[str] = []

    if recommended is None:
        return DealClassification(
            color=DealColor.GREEN,
            urgency_score=0.0,
            explanation="No flights found for this destination.",
            price_usd=0.0,
            value_savings_usd=0.0,
            positioning_savings_usd=0.0,
            effective_savings_usd=0.0,
            notes=["No route data."],
        )

    price = recommended.total_price
    typical = region.typical_price(comparison.destination)
    value_savings = round(max(0.0, typical - price), 2)

    positioning_savings = comparison.positioning_savings
    counted_positioning = (
        positioning_savings if comparison.recommend_positioning else 0.0
    )
    effective_savings = round(max(value_savings, counted_positioning), 2)

    if effective_savings >= config.red_min_savings_usd:
        color = DealColor.RED
    elif effective_savings >= config.yellow_min_savings_usd:
        color = DealColor.YELLOW
    else:
        color = DealColor.GREEN

    # A late-night arrival at a rule-bearing destination can never be RED.
    if color == DealColor.RED and arrival.has_rule and arrival.is_late_night:
        color = DealColor.YELLOW
        notes.append("Downgraded RED -> YELLOW: late-night arrival.")

    if arrival.note:
        notes.append(arrival.note)

    if comparison.recommend_positioning and comparison.direct is not None:
        extra = (
            recommended.travel_duration_hours
            - comparison.direct.travel_duration_hours
        )
        if extra >= LONG_DETOUR_HOURS:
            notes.append(
                f"Positioning adds ~{extra:.0f}h of travel time — confirm the "
                f"${effective_savings:,.0f} saved is worth it."
            )

    urgency = _score(price, typical, value_savings, counted_positioning, config, arrival)
    explanation = _explain(comparison, color, price, value_savings, counted_positioning)

    return DealClassification(
        color=color,
        urgency_score=round(urgency, 1),
        explanation=explanation,
        price_usd=price,
        value_savings_usd=value_savings,
        positioning_savings_usd=round(positioning_savings, 2),
        effective_savings_usd=effective_savings,
        notes=notes,
    )


def _score(price, typical, value_savings, positioning_savings, config, arrival) -> float:
    savings_pts = _clamp(
        positioning_savings / max(1.0, config.red_min_savings_usd) * 45.0, 0, 45
    )
    value_pts = _clamp(value_savings / max(1.0, typical) * 110.0, 0, 40)
    timing_pts = arrival.score_adjust if arrival.has_rule else 0.0
    return _clamp(savings_pts + value_pts + timing_pts + 6.0, 0.0, 100.0)


def _explain(comparison, color, price, value_savings, positioning_savings) -> str:
    parts = [f"{color.value}: best price ${price:,.0f}"]
    if value_savings > 0:
        parts.append(f"${value_savings:,.0f} under the typical fare")
    if comparison.recommend_positioning and positioning_savings > 0:
        parts.append(
            f"positioning via {comparison.recommended.gateway} saves "
            f"${positioning_savings:,.0f} vs. the direct route"
        )
    elif comparison.positioning_savings > 0 and not comparison.recommend_positioning:
        parts.append(
            f"positioning would only save ${comparison.positioning_savings:,.0f} "
            "— not worth the extra hop"
        )
    return "; ".join(parts) + "."


def classify_route(comparison: RouteComparison, config) -> DealResult:
    """Convenience: run the arrival check + classification together."""
    arrival = check_arrival(comparison.recommended, config)
    classification = classify(comparison, config, arrival)
    return DealResult(
        comparison=comparison, classification=classification, arrival=arrival
    )
