"""Echo — Price-context specialist.

Looks up the destination's typical price (from the Colombia region pack
when available, otherwise a Colombia-Desk default), classifies the
observed fare against the band, and emits a SpecialistReport.

Layer 6 activates the previously-reserved `lodging_signal` slot: when an
optional Layer 4 `LodgingIntelService` is injected (and a representative
observed nightly price is available), Echo consults it for the city-wide
lodging color and fills the slot. With no service injected, Echo behaves
exactly as it did through Layer 5 — `lodging_signal=None`, flag
`lodging-hook-reserved` — so every prior caller is unaffected.

Echo has no native lodging observation (its domain is flights), so the
representative nightly price is injected via `lodging_observed_usd`.
Sourcing that number from live nightly data is deferred to Layer 7; this
layer stays hermetic. No HTTP calls. No scraping.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
    # Optional Layer 4 lodging brain. Echo is fully functional without
    # it (lodging_signal stays None, exactly as through Layer 5); when
    # present AND lodging_observed_usd is supplied, Echo fills the slot.
    lodging_service: Optional[object] = None
    # Representative observed nightly price for the destination city.
    # Echo has no native lodging observation; live sourcing is Layer 7.
    lodging_observed_usd: Optional[float] = None

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

        lodging_signal, lodging_flag = self._consult_lodging(
            destination, event.observed_at.date()
        )

        payload = {
            "destination": destination,
            "observed_price_usd": event.price_usd,
            "typical_price_usd": typical,
            "label": position.label,
            "percent_of_typical": position.percent_of_typical,
            # Layer 6 hook — populated when the lodging brain is wired,
            # otherwise None (unchanged from Layer 3-5).
            "lodging_signal": lodging_signal,
        }

        flags = (lodging_flag,)
        verdict_input = {
            "price_position_label": position.label,
            "price_position_pct": round(position.percent_of_typical * 100, 1),
            "lodging_signal": lodging_signal,
        }

        # Echo's price-position math IS real; status tracks whether the
        # destination's typical band was available (unchanged from prior
        # layers — the lodging wiring does NOT alter Echo's status).
        status = Status.OK if destination in self.typical_prices else Status.PARTIAL
        confidence = 0.75 if status is Status.OK else 0.5

        log.info(
            "Echo report deal=%s dest=%s label=%s pct=%.1f%% status=%s lodging=%s",
            event.deal_id, destination, position.label,
            verdict_input["price_position_pct"], status.value,
            "none" if lodging_signal is None else lodging_signal.get("color"),
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

    def _consult_lodging(
        self, destination: str, on_date: date
    ) -> tuple[Optional[dict], str]:
        """Consult the Layer 4 lodging brain for the destination city.

        Returns ``(lodging_signal_dict, flag)``.

        - No service injected → ``(None, "lodging-hook-reserved")`` —
          byte-for-byte the Layer 3-5 behavior.
        - Service injected but no observed price / no baseline / it raises
          → ``(None, "lodging-signal-unavailable")`` (mirrors India's
          degrade-quietly contract).
        - Service yields a signal → ``(compact_dict, "lodging-wired")``.
        """
        if self.lodging_service is None:
            return None, "lodging-hook-reserved"
        if self.lodging_observed_usd is None:
            # Wired but nothing to score against (live nightly price is
            # a Layer 7 source). Degrade exactly like a missing baseline.
            return None, "lodging-signal-unavailable"
        try:
            sig = self.lodging_service.signal_for(
                observed_usd=float(self.lodging_observed_usd),
                city=destination,
                on_date=on_date,
            )
        except Exception:  # noqa: BLE001 — degrade quietly, never crash Echo
            log.exception("lodging_service.signal_for raised")
            return None, "lodging-signal-unavailable"
        if sig is None:
            return None, "lodging-signal-unavailable"
        return sig.as_verdict_dict(), "lodging-wired"

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
