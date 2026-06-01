"""Return-window coloring + ranking — pure, no I/O.

Given a PairingEstimate's options (each a priced ReturnOption), this module:

  1. Assigns a RED / YELLOW / GREEN color to every priced option, relative
     to the *median* round-trip total of the scanned window set. Cheap
     windows light up RED, mid-pack YELLOW, the rest GREEN. Thresholds are
     percentage-below-median and configurable.

  2. Ranks the options into the buckets Oak Street surfaces:
        cheapest_total       — lowest round-trip total
        cheapest_return_leg  — lowest *return* fare alone
        best_travel_time     — shortest return duration
        best_direct          — fewest stops, then cheapest
        top10                — cheapest N totals
        red / yellow         — colored buckets, cheapest-first
        avoid                — worst totals / most stops

Boundary rule: no network, no clock, no logging. Operates on the frozen
ReturnOption objects the pairing engine produced and returns frozen copies
(color filled in) plus a RankedReturns summary.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from .pairing import PairingEstimate, ReturnOption

# Default color thresholds: a window is RED when its round-trip total sits
# at or below (1 - RED_PCT) x median, YELLOW below (1 - YELLOW_PCT) x median.
RED_PCT = 0.15
YELLOW_PCT = 0.05


def _priced(options: tuple[ReturnOption, ...]) -> list[ReturnOption]:
    return [o for o in options if o.round_trip_total_usd is not None]


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def classify_returns(
    options: tuple[ReturnOption, ...],
    *,
    red_pct: float = RED_PCT,
    yellow_pct: float = YELLOW_PCT,
) -> tuple[ReturnOption, ...]:
    """Return a new option tuple with each priced option's `color` set.

    Unpriced options pass through untouched (color stays None). With a
    single priced option, the median equals that option's total, so it
    colors GREEN (not below median) — a sane, non-alarming default.
    """
    priced = _priced(options)
    if not priced:
        return options
    median = _median([o.round_trip_total_usd for o in priced])
    if median <= 0:
        return options

    out: list[ReturnOption] = []
    for o in options:
        if o.round_trip_total_usd is None:
            out.append(o)
            continue
        ratio = o.round_trip_total_usd / median
        if ratio <= 1.0 - red_pct:
            color = "RED"
        elif ratio <= 1.0 - yellow_pct:
            color = "YELLOW"
        else:
            color = "GREEN"
        out.append(replace(o, color=color))
    return tuple(out)


@dataclass(frozen=True)
class RankedReturns:
    """The ranked views Oak Street surfaces, all drawn from one option set."""
    cheapest_total: Optional[ReturnOption]
    cheapest_return_leg: Optional[ReturnOption]
    best_travel_time: Optional[ReturnOption]
    best_direct: Optional[ReturnOption]
    top10: tuple[ReturnOption, ...]
    red: tuple[ReturnOption, ...]
    yellow: tuple[ReturnOption, ...]
    avoid: tuple[ReturnOption, ...]
    median_total_usd: Optional[float]


def rank_returns(
    estimate: PairingEstimate,
    *,
    top_n: int = 10,
    avoid_n: int = 3,
    red_pct: float = RED_PCT,
    yellow_pct: float = YELLOW_PCT,
) -> tuple[tuple[ReturnOption, ...], RankedReturns]:
    """Color then rank. Returns (colored_options, RankedReturns).

    `colored_options` is the full option list with colors assigned (in the
    original window order) so callers can render the per-day table; the
    RankedReturns holds the derived bucket views.
    """
    colored = classify_returns(
        estimate.options, red_pct=red_pct, yellow_pct=yellow_pct
    )
    priced = _priced(colored)
    if not priced:
        return colored, RankedReturns(
            cheapest_total=None, cheapest_return_leg=None,
            best_travel_time=None, best_direct=None,
            top10=(), red=(), yellow=(), avoid=(), median_total_usd=None,
        )

    by_total = sorted(priced, key=lambda o: o.round_trip_total_usd)
    cheapest_total = by_total[0]
    cheapest_return_leg = min(priced, key=lambda o: o.return_price_usd)

    # Travel time: only among options that reported a duration; cheapest
    # total breaks ties so the "fast" pick is also a sensible price.
    timed = [o for o in priced if o.duration_minutes is not None]
    best_travel_time = (
        min(timed, key=lambda o: (o.duration_minutes, o.round_trip_total_usd))
        if timed else None
    )
    # Least-hassle: fewest stops, then cheapest total.
    best_direct = min(priced, key=lambda o: (o.stops, o.round_trip_total_usd))

    top10 = tuple(by_total[:top_n])
    red = tuple(o for o in by_total if o.color == "RED")
    yellow = tuple(o for o in by_total if o.color == "YELLOW")
    # Avoid: the most expensive totals (worst value), most-expensive first.
    avoid = tuple(reversed(by_total[-avoid_n:])) if len(by_total) > avoid_n else ()

    return colored, RankedReturns(
        cheapest_total=cheapest_total,
        cheapest_return_leg=cheapest_return_leg,
        best_travel_time=best_travel_time,
        best_direct=best_direct,
        top10=top10,
        red=red,
        yellow=yellow,
        avoid=avoid,
        median_total_usd=round(_median([o.round_trip_total_usd for o in priced]), 2),
    )
