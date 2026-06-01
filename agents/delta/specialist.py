"""Delta — Return Pairing specialist (Stage 2: live optimizer).

Consumes an outbound AlertEvent and emits a SpecialistReport whose payload
carries, for every return window (4–60 days after departure):

    - the priced return leg with whatever REAL itinerary detail the source
      returned (airline, departure/arrival, duration, stops, booking link),
    - a RED / YELLOW / GREEN color relative to the window-set median, and
    - ranked views (cheapest total, cheapest return, fastest, most-direct,
      top-10, red/yellow buckets, and an avoid list).

Two fetch postures:

    placeholder (default, offline)  — deterministic stub prices; the report
        is clearly labelled as placeholder and never presents the data as
        real airline information.
    live (DELTA_LIVE_RETURNS=true)  — prices return legs from the same
        verified LiveFlightFetcher the outbound scanner already uses, with
        day-sampling to stay inside the provider's quota.

Honesty rule (load-bearing): fields a provider does not return — flight
numbers, connection cities, layover duration on the Skyscanner endpoint —
are left empty, never synthesized. The renderer prints "not provided by
source" for them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from agents.logging_setup import get_logger
from agents.oakstreet.orchestrator import AlertEvent
from agents.specialist_report import SpecialistReport, Status
from intel.return_pairing import (
    PairingEstimate,
    ReturnLegFetcher,
    ReturnLegQuote,
    ReturnOption,
    combo_color,
    estimate_pairing,
    parse_fixed_list,
    qualifies,
    rank_returns,
    resolve_return_windows,
)

log = get_logger("delta")

_TRUE = {"1", "true", "yes", "on"}


def placeholder_return_fetcher(
    origin: str, destination: str, return_date: date
) -> Optional[float]:
    """Deterministic stub: prices a return leg from heuristic anchors.

    Used so the Delta specialist, the pairing engine, and the Oak Street
    ingestion path are all exercisable without a live API. Numbers are
    plausible-but-fictional; do NOT treat outputs as real fares.
    """
    base_by_origin = {
        "BOG": 240.0, "MDE": 260.0, "CLO": 290.0,
        "CTG": 220.0, "BAQ": 270.0, "SMR": 320.0,
    }
    base = base_by_origin.get(origin.upper(), 280.0)
    # Mild seasonality bump in Dec/Jan; otherwise flat.
    seasonal = 35.0 if return_date.month in (12, 1) else 0.0
    # Mid-stay returns (21–30d) trend slightly cheaper, edges trend higher.
    days_off_axis = abs((return_date.toordinal() % 7) - 3)  # 0..3
    weekday_bump = 12.0 * days_off_axis
    return round(base + seasonal + weekday_bump, 2)


# --- FlightOffer -> ReturnLegQuote adapters --------------------------------

def _offer_to_quote(offer) -> ReturnLegQuote:
    """Map a scanner FlightOffer into a return-pairing ReturnLegQuote.

    Carries provenance (offer.source) so a 429-fallback day arrives tagged
    'placeholder' and the renderer never presents it as live airline data.
    """
    return ReturnLegQuote(
        price_usd=offer.price_usd,
        airline=offer.airline,
        stops=offer.stops,
        depart_iso=offer.depart_dt.isoformat(),
        arrive_iso=offer.arrive_dt.isoformat(),
        duration_minutes=offer.duration_minutes,
        booking_url=offer.booking_url,
        source=offer.source,
        flight_numbers=offer.flight_numbers,
        connections=offer.connections,
    )


def _offer_fetcher(flight_fetcher) -> ReturnLegFetcher:
    """Wrap any scanner FlightFetcher into a (o, d, when) -> ReturnLegQuote.

    Picks the cheapest offer for the route/day. Works in either direction,
    so the same fetcher prices both the outbound enrichment leg and each
    return window.
    """
    def fetch(origin: str, destination: str, when: date) -> Optional[ReturnLegQuote]:
        try:
            offers = flight_fetcher.search(origin, destination, when)
        except Exception as exc:  # noqa: BLE001 — a bad day must not abort the scan
            log.warning("return-leg search %s->%s %s failed: %s",
                        origin, destination, when, exc)
            return None
        if not offers:
            return None
        return _offer_to_quote(min(offers, key=lambda o: o.price_usd))
    return fetch


def make_placeholder_offer_fetcher() -> ReturnLegFetcher:
    """A richer placeholder fetcher that returns full (labelled) quotes.

    Unlike `placeholder_return_fetcher` (price-only), this surfaces the
    deterministic airline/time/duration fields so a DRY_RUN report renders
    the full layout — every row tagged source='placeholder'.
    """
    from src.flight_fetcher import PlaceholderFlightFetcher
    return _offer_fetcher(PlaceholderFlightFetcher())


def make_live_return_fetcher(config=None) -> ReturnLegFetcher:
    """A live fetcher backed by the verified scanner LiveFlightFetcher.

    Reuses the connector the outbound scan already trusts (caching,
    cooldown, graceful placeholder fallback). On a fallback day the offer
    carries source='placeholder', so provenance stays honest downstream.
    """
    from src.config import load_config
    from src.flight_fetcher import get_fetcher
    cfg = config if config is not None else load_config()
    return _offer_fetcher(get_fetcher(cfg))


# --- day sampling (quota control for the live path) ------------------------

def sampled_return_days(
    windows: tuple[int, ...], *, dense_max: int = 14, sparse_step: int = 4
) -> tuple[int, ...]:
    """Reduce a dense window list to a quota-friendly sample.

    Every day up to `dense_max` is kept; beyond it, every `sparse_step`-th
    day is kept; the final day is always included. (4..60 → ~23 days.)
    """
    days = sorted(set(windows))
    if not days:
        return ()
    out = [d for d in days
           if d <= dense_max or (d - dense_max) % max(1, sparse_step) == 0]
    if days[-1] not in out:
        out.append(days[-1])
    return tuple(sorted(set(out)))


def _resolve_sample(windows: tuple[int, ...]) -> tuple[int, ...]:
    """Pick the live sample set from the environment."""
    explicit = os.environ.get("DELTA_RETURN_DAYS")
    if explicit:
        return parse_fixed_list(explicit)
    dense_max = int(os.environ.get("DELTA_RETURN_DENSE_MAX", "14"))
    sparse_step = int(os.environ.get("DELTA_RETURN_SPARSE_STEP", "4"))
    return sampled_return_days(windows, dense_max=dense_max, sparse_step=sparse_step)


def _live_enabled() -> bool:
    return os.environ.get("DELTA_LIVE_RETURNS", "").strip().lower() in _TRUE


@dataclass
class Delta:
    """Return Pairing specialist.

    The active window list is resolved once at construction from the
    environment via `resolve_return_windows()`. Pass `windows=` to bypass
    env resolution. Pass `fetcher=` to inject a deterministic fetcher
    (tests and any caller needing reproducible prices should do so).

    With no `fetcher` provided, Delta resolves one from the environment:
    a live fetcher when DELTA_LIVE_RETURNS is true, otherwise the offline
    placeholder. Whichever it is determines the report's provenance and
    whether the window list is sampled for quota.
    """
    fetcher: Optional[ReturnLegFetcher] = None
    windows: tuple[int, ...] | None = None
    # Set in __post_init__; "live" | "placeholder".
    _provenance: str = field(default="placeholder", init=False)
    _sampled: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        explicit_fetcher = self.fetcher is not None
        explicit_windows = self.windows is not None

        if self.windows is None:
            # Bind once at construction — re-reading os.environ on every
            # analyze() risks subtle drift inside a long-running process.
            self.windows = resolve_return_windows()

        if not explicit_fetcher and _live_enabled():
            # Live posture: real connector + quota-friendly day sampling
            # (only auto-sample env-resolved windows, never explicit ones).
            self.fetcher = make_live_return_fetcher()
            self._provenance = "live"
            if not explicit_windows:
                self.windows = _resolve_sample(self.windows)
                self._sampled = True
        elif not explicit_fetcher:
            # Default offline posture — price-only placeholder. STUB status.
            self.fetcher = placeholder_return_fetcher
            self._provenance = "placeholder"
        else:
            # An injected fetcher is treated as placeholder-grade for status
            # purposes (preserves prior STUB-on-injection behavior).
            self._provenance = "placeholder"

    def analyze(
        self,
        event: AlertEvent,
        *,
        origin: str = "BWI",
        windows: tuple[int, ...] | None = None,
    ) -> SpecialistReport:
        """Pair the outbound observation with each return window.

        Per-call `windows=` overrides the construction-bound list. DRY_RUN-
        safe: the specialist never sends anywhere. Oak Street decides
        whether the report is rendered, recorded, or suppressed.
        """
        active_windows = windows if windows is not None else self.windows
        destination = self._destination_from_route(event.route_signature)
        outbound_depart = event.departure_at.date()

        estimate: PairingEstimate = estimate_pairing(
            origin=origin,
            destination=destination,
            outbound_depart=outbound_depart,
            outbound_price_usd=event.price_usd,
            fetcher=self.fetcher,
            windows=active_windows,
        )
        # Enrich the OUTBOUND leg (airline / times / booking link) from the
        # same fetcher. Falls back to the event's price-only data.
        outbound = self._outbound_detail(origin, destination, outbound_depart, event)

        return self._to_report(event, estimate, outbound, observed_at=event.observed_at)

    # --- internals --------------------------------------------------------

    def _outbound_detail(
        self, origin: str, destination: str, depart: date, event: AlertEvent
    ) -> dict:
        """Best-effort full detail for the outbound leg."""
        detail = {
            "origin": origin,
            "destination": destination,
            "depart_date": depart.isoformat(),
            "price_usd": round(event.price_usd, 2),
            "color": (event.color or "").upper(),
            "route_signature": event.route_signature,
        }
        try:
            quote = self.fetcher(origin, destination, depart)
        except Exception:  # noqa: BLE001 — enrichment is optional
            quote = None
        if isinstance(quote, ReturnLegQuote):
            detail.update({
                "airline": quote.airline,
                "stops": quote.stops,
                "route_type": _route_type(quote.stops),
                "depart_iso": quote.depart_iso,
                "arrive_iso": quote.arrive_iso,
                "duration_minutes": quote.duration_minutes,
                "booking_url": quote.booking_url,
                "source": quote.source,
                "flight_numbers": list(quote.flight_numbers),
                "connections": list(quote.connections),
                "cabin": quote.cabin,
            })
        return detail

    def _destination_from_route(self, route_signature: str) -> str:
        """Extract the rightmost airport code from a route signature.

        Accepts both 'BWI->BOG direct' and 'BWI->MIA->BOG' shapes; falls
        back to 'BOG' if parsing fails (Colombia-only desk default).
        """
        if not route_signature:
            return "BOG"
        tail = route_signature.split("->")[-1].strip()
        code = tail.split()[0] if tail else ""
        return code.upper() if code else "BOG"

    def _to_report(
        self,
        event: AlertEvent,
        estimate: PairingEstimate,
        outbound: dict,
        *,
        observed_at: datetime,
    ) -> SpecialistReport:
        # Color + rank the full option set.
        colored, ranked = rank_returns(estimate)
        priced_count = sum(
            1 for o in colored if o.round_trip_total_usd is not None
        )
        total_count = len(colored)
        live = self._provenance == "live"

        if priced_count == 0:
            status = Status.NO_DATA
            confidence = 0.0
        elif priced_count < total_count:
            status = Status.PARTIAL
            confidence = priced_count / total_count
        elif live:
            status = Status.OK
            confidence = 0.9
        else:
            # Fully-priced placeholder data is still a stub — label it so
            # Oak Street can present it as foundation-stage, not live.
            status = Status.STUB
            confidence = 0.6

        best = ranked.cheapest_total

        # --- Phase 2.7: round-trip combo classification --------------------
        # Pair the OUTBOUND leg color (from the scanner's deal classifier,
        # carried on the AlertEvent) with each RETURN leg's color (from the
        # ranking pass). Both legs at least YELLOW => alert-worthy combo.
        outbound_color = (event.color or "").upper()
        rt_typical = _round_trip_typical(estimate.destination)

        def _to_dict(o: Optional[ReturnOption]) -> Optional[dict]:
            return _option_to_dict(
                o, outbound_color=outbound_color, round_trip_typical=rt_typical
            )

        option_dicts = [_to_dict(o) for o in colored]
        qualifying = [
            d for d in option_dicts
            if d is not None and d.get("qualifies")
            and d.get("round_trip_total_usd") is not None
        ]
        best_qualifying = (
            min(qualifying, key=lambda d: d["round_trip_total_usd"])
            if qualifying else None
        )

        payload = {
            "origin": estimate.origin,
            "destination": estimate.destination,
            "outbound_depart": estimate.outbound_depart.isoformat(),
            "outbound_price_usd": estimate.outbound_price_usd,
            "outbound_color": outbound_color,
            "round_trip_typical_usd": rt_typical,
            "provenance": self._provenance,
            "sampled": self._sampled,
            "window_count": total_count,
            "priced_count": priced_count,
            "qualifying_count": len(qualifying),
            "best_qualifying": best_qualifying,
            "median_total_usd": ranked.median_total_usd,
            "outbound": outbound,
            "options": option_dicts,
            "ranking": {
                "cheapest_total": _to_dict(ranked.cheapest_total),
                "cheapest_return_leg": _to_dict(ranked.cheapest_return_leg),
                "best_travel_time": _to_dict(ranked.best_travel_time),
                "best_direct": _to_dict(ranked.best_direct),
                "top10": [_to_dict(o) for o in ranked.top10],
                "red": [_to_dict(o) for o in ranked.red],
                "yellow": [_to_dict(o) for o in ranked.yellow],
                "avoid": [_to_dict(o) for o in ranked.avoid],
            },
        }

        flags: list[str] = []
        if status is Status.STUB:
            flags.append("placeholder-fetcher")
        if priced_count < total_count and priced_count > 0:
            flags.append("partial-window-coverage")
        if live and any(o.source == "placeholder"
                        for o in colored if o.round_trip_total_usd is not None):
            # Some live days fell back to placeholder (cooldown / 429).
            flags.append("mixed-provenance")
        if qualifying:
            # At least one round trip has both legs >= YELLOW.
            flags.append("round-trip-combo")

        verdict_input: dict = {}
        if best is not None:
            verdict_input["round_trip_est_usd"] = best.round_trip_total_usd
            verdict_input["best_return_window_days"] = best.window_days

        log.info(
            "Delta report deal=%s prov=%s status=%s priced=%d/%d best=%s",
            event.deal_id, self._provenance, status.value,
            priced_count, total_count,
            (best.round_trip_total_usd if best else None),
        )
        return SpecialistReport(
            agent="delta",
            status=status,
            confidence=round(confidence, 3),
            deal_id=event.deal_id,
            observed_at=observed_at,
            payload=payload,
            flags=tuple(flags),
            verdict_input=verdict_input,
        )


def _route_type(stops: int) -> str:
    if stops <= 0:
        return "direct"
    if stops == 1:
        return "one stop"
    return f"{stops} stops"


def _round_trip_typical(destination: str) -> Optional[float]:
    """Best-effort round-trip typical baseline for the destination.

    Defined as 2x the active region pack's one-way typical fare (there is no
    separate return-typical in the pack, and typical fares are treated as
    symmetric). Returns None when no region is active (e.g. some unit tests)
    so the report degrades to "— not provided" rather than crashing.
    """
    try:
        from src import region
        return round(2.0 * region.typical_price(destination), 2)
    except Exception:  # noqa: BLE001 — typical is an optional annotation
        return None


def _option_to_dict(
    o: Optional[ReturnOption],
    *,
    outbound_color: Optional[str] = None,
    round_trip_typical: Optional[float] = None,
) -> Optional[dict]:
    """Serialize a ReturnOption (or None) to a JSON-safe dict.

    Phase 2.7: when ``outbound_color`` is supplied, the dict also carries the
    round-trip combo category (outbound x return leg colors), a ``qualifies``
    flag, and ``savings_vs_typical_usd`` (round-trip typical minus total).
    """
    if o is None:
        return None
    total = o.round_trip_total_usd
    combo = combo_color(outbound_color, o.color)
    savings_vs_typical = (
        round(round_trip_typical - total, 2)
        if isinstance(round_trip_typical, (int, float))
        and isinstance(total, (int, float))
        else None
    )
    return {
        "window_days": o.window_days,
        "return_date": o.return_date.isoformat(),
        "return_price_usd": o.return_price_usd,
        "round_trip_total_usd": total,
        "confidence": o.confidence,
        "airline": o.airline,
        "stops": o.stops,
        "route_type": _route_type(o.stops),
        "depart_iso": o.depart_iso,
        "arrive_iso": o.arrive_iso,
        "duration_minutes": o.duration_minutes,
        "booking_url": o.booking_url,
        "source": o.source,
        "flight_numbers": list(o.flight_numbers),
        "connections": list(o.connections),
        "cabin": o.cabin,
        "color": o.color,
        # --- Phase 2.7 round-trip combo fields ---
        "outbound_color": (outbound_color or "").upper() or None,
        "return_color": o.color,
        "combo_color": combo,
        "qualifies": qualifies(outbound_color, o.color),
        "round_trip_typical_usd": round_trip_typical,
        "savings_vs_typical_usd": savings_vs_typical,
    }
