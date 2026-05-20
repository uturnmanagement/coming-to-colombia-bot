"""Compare direct routes against gateway-positioning routes.

Strategy A: origin -> destination (one booking).
Strategy B: origin -> gateway, then gateway -> destination (two bookings).

Origin and gateway choices come entirely from the active region pack, so
this works for any market the framework is configured for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import region
from .flight_fetcher import FlightFetcher, FlightOffer

# Minimum connection gap between a positioning leg and the onward flight.
MIN_CONNECTION_HOURS = 1.5


@dataclass
class RouteOption:
    """A complete way to get from the origin to a destination."""

    strategy: str  # "direct" or "positioning"
    legs: list[FlightOffer]
    gateway: str | None = None

    @property
    def total_price(self) -> float:
        return round(sum(leg.price_usd for leg in self.legs), 2)

    @property
    def origin(self) -> str:
        return self.legs[0].origin

    @property
    def final_destination(self) -> str:
        return self.legs[-1].destination

    @property
    def depart_dt(self) -> datetime:
        return self.legs[0].depart_dt

    @property
    def final_arrival_dt(self) -> datetime:
        return self.legs[-1].arrive_dt

    @property
    def travel_duration_hours(self) -> float:
        return (self.final_arrival_dt - self.depart_dt).total_seconds() / 3600.0

    @property
    def layover_hours(self) -> float:
        if len(self.legs) < 2:
            return 0.0
        return (self.legs[1].depart_dt - self.legs[0].arrive_dt).total_seconds() / 3600.0

    def describe(self) -> str:
        if self.strategy == "direct":
            return (
                f"{region.city_label(self.origin)} -> "
                f"{region.city_label(self.final_destination)} (direct booking)"
            )
        return (
            f"{region.city_label(self.origin)} -> {region.city_label(self.gateway)} "
            f"-> {region.city_label(self.final_destination)} (positioning)"
        )


@dataclass
class RouteComparison:
    """Direct vs positioning analysis for one destination."""

    destination: str
    direct: RouteOption | None = None
    positioning: RouteOption | None = None
    all_positioning: list[RouteOption] = field(default_factory=list)
    recommended: RouteOption | None = None
    recommend_positioning: bool = False
    positioning_savings: float = 0.0

    @property
    def cheapest_price(self) -> float:
        return self.recommended.total_price if self.recommended else 0.0


def _cheapest(offers: list[FlightOffer]) -> FlightOffer | None:
    return min(offers, key=lambda o: o.price_usd) if offers else None


def _best_positioning_for_gateway(
    leg1_options: list[FlightOffer],
    leg2_options: list[FlightOffer],
    gateway: str,
    max_layover_hours: float,
) -> RouteOption | None:
    """Pick the cheapest valid leg1 + leg2 pairing through one gateway."""
    best: RouteOption | None = None
    for leg1 in leg1_options:
        earliest = leg1.arrive_dt + timedelta(hours=MIN_CONNECTION_HOURS)
        for leg2 in leg2_options:
            if leg2.depart_dt < earliest:
                continue
            layover = (leg2.depart_dt - leg1.arrive_dt).total_seconds() / 3600.0
            if layover > max_layover_hours:
                continue
            option = RouteOption("positioning", [leg1, leg2], gateway=gateway)
            if best is None or option.total_price < best.total_price:
                best = option
    return best


def compare_routes(
    fetcher: FlightFetcher,
    destination: str,
    config,
    depart_day: date,
) -> RouteComparison:
    """Build a full direct-vs-positioning comparison for one destination."""
    destination = destination.upper()
    origin = region.origin()
    comparison = RouteComparison(destination=destination)

    # Strategy A: direct origin -> destination.
    direct_offers = fetcher.search(origin, destination, depart_day)
    cheapest_direct = _cheapest(direct_offers)
    if cheapest_direct is not None:
        comparison.direct = RouteOption("direct", [cheapest_direct])

    # Strategy B: origin -> gateway -> destination.
    next_day = depart_day + timedelta(days=1)
    for gateway in region.gateways_for(destination):
        leg1_options = fetcher.search(origin, gateway, depart_day)
        leg2_options = (
            fetcher.search(gateway, destination, depart_day)
            + fetcher.search(gateway, destination, next_day)
        )
        option = _best_positioning_for_gateway(
            leg1_options, leg2_options, gateway, config.max_acceptable_layover_hours
        )
        if option is not None:
            comparison.all_positioning.append(option)

    comparison.all_positioning.sort(key=lambda o: o.total_price)
    if comparison.all_positioning:
        comparison.positioning = comparison.all_positioning[0]

    _choose_recommendation(comparison, config)
    return comparison


def _choose_recommendation(comparison: RouteComparison, config) -> None:
    """Recommend positioning only when it clears the min-savings bar."""
    direct = comparison.direct
    positioning = comparison.positioning

    if direct and positioning:
        comparison.positioning_savings = round(
            direct.total_price - positioning.total_price, 2
        )
        worth_it = (
            positioning.total_price < direct.total_price
            and comparison.positioning_savings >= config.positioning_min_savings_usd
        )
        if worth_it:
            comparison.recommended = positioning
            comparison.recommend_positioning = True
        else:
            comparison.recommended = direct
            comparison.recommend_positioning = False
    elif direct:
        comparison.recommended = direct
        comparison.recommend_positioning = False
    elif positioning:
        comparison.recommended = positioning
        comparison.recommend_positioning = True
