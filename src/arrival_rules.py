"""Generic per-destination arrival-time rules.

Some destinations have airports far from the city, or limited / pricey
late-night ground transport. A region pack can attach `arrival_rules` to
any destination; this module scores the final arrival time against them.

This generalizes the original Medellin-specific logic — Medellin is now
just one destination in colombia.yaml that happens to carry an
arrival_rules block.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import region

PREFERRED_BONUS = 12.0
LATE_NIGHT_PENALTY = -22.0


@dataclass
class ArrivalCheck:
    has_rule: bool
    destination: str
    arrival_hour: int
    arrival_label: str
    is_late_night: bool
    is_preferred_window: bool
    score_adjust: float
    warning: str | None
    note: str


def _neutral(destination: str = "") -> ArrivalCheck:
    return ArrivalCheck(
        has_rule=False,
        destination=destination,
        arrival_hour=-1,
        arrival_label="",
        is_late_night=False,
        is_preferred_window=False,
        score_adjust=0.0,
        warning=None,
        note="",
    )


def check_arrival(route_option, config) -> ArrivalCheck:
    """Evaluate the final arrival time against the destination's rule."""
    if route_option is None:
        return _neutral()

    destination = route_option.final_destination
    pack = config.region if (config and config.region) else region.active()
    rule = pack.arrival_rule(destination)
    if rule is None:
        return _neutral(destination)

    arrival = route_option.final_arrival_dt
    hour = arrival.hour
    label = arrival.strftime("%H:%M")
    city = pack.city_label(destination)

    is_late_night = hour >= rule.late_night_start or hour < 5
    is_preferred = rule.preferred_start <= hour <= rule.preferred_end

    if is_late_night:
        return ArrivalCheck(
            has_rule=True,
            destination=destination,
            arrival_hour=hour,
            arrival_label=label,
            is_late_night=True,
            is_preferred_window=False,
            score_adjust=LATE_NIGHT_PENALTY,
            warning=(
                f"⚠️ {city} arrival at {label} is late night — ground transport "
                "is limited and pricier; arrange a ride in advance."
            ),
            note=f"Late-night {destination} arrival (penalized).",
        )

    if is_preferred:
        return ArrivalCheck(
            has_rule=True,
            destination=destination,
            arrival_hour=hour,
            arrival_label=label,
            is_late_night=False,
            is_preferred_window=True,
            score_adjust=PREFERRED_BONUS,
            warning=None,
            note=f"Arrives {destination} {label} — preferred window.",
        )

    return ArrivalCheck(
        has_rule=True,
        destination=destination,
        arrival_hour=hour,
        arrival_label=label,
        is_late_night=False,
        is_preferred_window=False,
        score_adjust=0.0,
        warning=None,
        note=f"Arrives {destination} {label} — acceptable timing.",
    )
