"""Echo — Price-context specialist (foundation shell).

Looks up the destination's typical price (from the Colombia region pack
when available, otherwise a Colombia-Desk default), classifies the
observed fare against the band, and emits a SpecialistReport.

Lodging-intelligence is reserved at the schema boundary (the
`lodging_signal` slot in verdict_input) but explicitly NOT activated
here — that work belongs to a later layer. No HTTP calls. No scraping.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.logging_setup import get_logger
from agents.oakstreet.orchestrator import AlertEvent
from agents.specialist_report import SpecialistReport, Status
from intel.price_context import PriceBand, classify_price_position

log = get_logger("echo")


# Conservative Colombia-Desk default when the region pack can't be
# consulted (e.g. in unit tests). The colombia.yaml region pack lists
# its own per-destination typical_price_usd which the specialist
# prefers when available.
DEFAULT_TYPICAL_PRICE_USD = 330.0


@dataclass
class Echo:
    """Price-context specialist."""
    typical_prices: dict[str, float] = None  # destination -> typical USD

    def __post_init__(self) -> None:
        if self.typical_prices is None:
            # Lazy-resolve from the active region pack. The desk is
            # Colombia-only in Layer 3, so this is the only path
            # that needs to load region data.
            self.typical_prices = self._load_from_region_pack()

    def analyze(self, event: AlertEvent) -> SpecialistReport:
        """Classify the observed price against the destination's band."""
        destination = self._destination_from_route(event.route_signature)
        typical = self.typical_prices.get(destination, DEFAULT_TYPICAL_PRICE_USD)
        band = PriceBand(typical_usd=typical)
        position = classify_price_position(event.price_usd, band)

        payload = {
            "destination": destination,
            "observed_price_usd": event.price_usd,
            "typical_price_usd": typical,
            "label": position.label,
            "percent_of_typical": position.percent_of_typical,
            # Layer 4 hook (intentionally None in Layer 3):
            "lodging_signal": None,
        }

        flags = ("lodging-hook-reserved",)
        verdict_input = {
            "price_position_label": position.label,
            "price_position_pct": round(position.percent_of_typical * 100, 1),
            "lodging_signal": None,
        }

        # Echo's price-position math IS real; the lodging path is the
        # stub. Reflect that by reporting OK with a moderate confidence
        # rather than STUB. Move to STUB only if typical was unavailable.
        status = Status.OK if destination in self.typical_prices else Status.PARTIAL
        confidence = 0.75 if status is Status.OK else 0.5

        log.info(
            "Echo report deal=%s dest=%s label=%s pct=%.1f%% status=%s",
            event.deal_id, destination, position.label,
            verdict_input["price_position_pct"], status.value,
        )
        return SpecialistReport(
            agent="echo",
            status=status,
            confidence=confidence,
            deal_id=event.deal_id,
            observed_at=event.observed_at,
            payload=payload,
            flags=flags,
            verdict_input=verdict_input,
        )

    # --- internals --------------------------------------------------------

    def _destination_from_route(self, route_signature: str) -> str:
        if not route_signature:
            return "BOG"
        tail = route_signature.split("->")[-1].strip()
        code = tail.split()[0] if tail else ""
        return code.upper() if code else "BOG"

    def _load_from_region_pack(self) -> dict[str, float]:
        """Best-effort load of per-destination typical prices from the
        scanner's active region pack. Falls back to an empty dict if
        the region pack is not available (e.g. in unit tests)."""
        try:
            from src.region import active as _active_region
            pack = _active_region()
            return {
                code: float(getattr(d, "typical_price_usd", 0) or 0)
                for code, d in pack.destinations.items()
                if getattr(d, "typical_price_usd", None)
            }
        except Exception:  # noqa: BLE001 — region not loaded is fine
            return {}
