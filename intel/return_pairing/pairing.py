"""Pure return-pairing engine.

Given an outbound fare and a fetcher that prices return legs, produce a
`PairingEstimate` that lists every candidate window with a round-trip
total. The fetcher is a protocol so Layer 3 can run on a placeholder
without an API key. Live fetching is Layer 4+ work.

Boundary rule: no network, no clock, no logging in this module. The
specialist shell calls into it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .windows import RETURN_WINDOWS_DAYS, generate_windows


@dataclass(frozen=True)
class ReturnLegQuote:
    """A priced return leg with whatever real itinerary detail the source
    supplied. A fetcher MAY still return a bare ``float`` (legacy /
    placeholder) — ``estimate_pairing`` normalizes both. Fields that the
    provider does not return stay empty; they are never synthesized.
    """
    price_usd: float
    airline: str = ""
    stops: int = 0
    depart_iso: Optional[str] = None
    arrive_iso: Optional[str] = None
    duration_minutes: Optional[int] = None
    booking_url: str = ""
    source: str = ""                      # "live" | "placeholder"
    flight_numbers: tuple[str, ...] = ()  # empty unless provider supplies
    connections: tuple[str, ...] = ()
    cabin: Optional[str] = None


# A return-leg fetcher takes (origin, destination, return_date) where
# origin/destination are the *return* directions (so the inbound's
# original destination is now the fetcher's origin). It returns either a
# USD float, a ReturnLegQuote, or None when no data is available.
ReturnLegFetcher = Callable[[str, str, date], Optional[object]]


def _normalize_quote(value: object) -> Optional[ReturnLegQuote]:
    """Coerce a fetcher result into a ReturnLegQuote (or None).

    Accepts a ReturnLegQuote as-is, wraps a number into a price-only quote
    (legacy float fetchers), and treats anything else / None as no data.
    """
    if value is None:
        return None
    if isinstance(value, ReturnLegQuote):
        return value
    if isinstance(value, (int, float)):
        return ReturnLegQuote(price_usd=float(value))
    return None


@dataclass(frozen=True)
class ReturnOption:
    window_days: int
    return_date: date
    return_price_usd: Optional[float]
    round_trip_total_usd: Optional[float]
    confidence: float           # 0..1 — degrades when data is missing
    # --- Stage 2 enrichment (defaults keep older callers/tests valid) ---
    airline: str = ""
    stops: int = 0
    depart_iso: Optional[str] = None
    arrive_iso: Optional[str] = None
    duration_minutes: Optional[int] = None
    booking_url: str = ""
    source: str = ""
    flight_numbers: tuple[str, ...] = ()
    connections: tuple[str, ...] = ()
    cabin: Optional[str] = None
    color: Optional[str] = None  # assigned by the ranking pass (RED/YELLOW/GREEN)


@dataclass(frozen=True)
class PairingEstimate:
    origin: str
    destination: str
    outbound_depart: date
    outbound_price_usd: float
    options: tuple[ReturnOption, ...] = field(default_factory=tuple)

    @property
    def best_option(self) -> Optional[ReturnOption]:
        """Cheapest fully-priced option; None if every window is missing data."""
        priced = [o for o in self.options if o.round_trip_total_usd is not None]
        if not priced:
            return None
        return min(priced, key=lambda o: o.round_trip_total_usd)


def estimate_pairing(
    *,
    origin: str,
    destination: str,
    outbound_depart: date,
    outbound_price_usd: float,
    fetcher: ReturnLegFetcher,
    windows=RETURN_WINDOWS_DAYS,
) -> PairingEstimate:
    """Pair an outbound deal with each return window. No I/O of its own."""
    options: list[ReturnOption] = []
    for days, return_date in generate_windows(outbound_depart, windows=windows):
        # Note the swap: returning is destination -> origin.
        quote = _normalize_quote(fetcher(destination, origin, return_date))
        if quote is None:
            options.append(ReturnOption(
                window_days=days,
                return_date=return_date,
                return_price_usd=None,
                round_trip_total_usd=None,
                confidence=0.0,
            ))
            continue
        total = round(outbound_price_usd + quote.price_usd, 2)
        options.append(ReturnOption(
            window_days=days,
            return_date=return_date,
            return_price_usd=round(quote.price_usd, 2),
            round_trip_total_usd=total,
            confidence=1.0,
            airline=quote.airline,
            stops=quote.stops,
            depart_iso=quote.depart_iso,
            arrive_iso=quote.arrive_iso,
            duration_minutes=quote.duration_minutes,
            booking_url=quote.booking_url,
            source=quote.source,
            flight_numbers=quote.flight_numbers,
            connections=quote.connections,
            cabin=quote.cabin,
        ))
    return PairingEstimate(
        origin=origin,
        destination=destination,
        outbound_depart=outbound_depart,
        outbound_price_usd=round(outbound_price_usd, 2),
        options=tuple(options),
    )
