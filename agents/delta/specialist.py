"""Delta — Return Pairing specialist shell.

Consumes an outbound AlertEvent and emits a SpecialistReport whose
verdict_input carries the cheapest round-trip estimate and the best
return-window length. Oak Street decides whether and how to surface
the result in the final briefing.

Layer 3 is foundation: the default fetcher is a deterministic
placeholder so the schema, the pairing math, and the ingestion path
can all be exercised offline. Wiring a live fetcher (Skyscanner /
Amadeus) is Layer 4 work.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from agents.logging_setup import get_logger
from agents.oakstreet.orchestrator import AlertEvent
from agents.specialist_report import SpecialistReport, Status
from intel.return_pairing import (
    PairingEstimate,
    ReturnLegFetcher,
    RETURN_WINDOWS_DAYS,
    estimate_pairing,
)

log = get_logger("delta")


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


@dataclass
class Delta:
    """Return Pairing specialist."""
    fetcher: ReturnLegFetcher = placeholder_return_fetcher

    def analyze(
        self,
        event: AlertEvent,
        *,
        origin: str = "BWI",
        windows=RETURN_WINDOWS_DAYS,
    ) -> SpecialistReport:
        """Pair the outbound observation with each return window.

        DRY_RUN-safe: the specialist itself never sends anywhere. Oak
        Street decides whether the report is rendered, recorded, or
        suppressed.
        """
        destination = self._destination_from_route(event.route_signature)
        outbound_depart = event.departure_at.date()
        estimate: PairingEstimate = estimate_pairing(
            origin=origin,
            destination=destination,
            outbound_depart=outbound_depart,
            outbound_price_usd=event.price_usd,
            fetcher=self.fetcher,
            windows=windows,
        )

        return self._to_report(event, estimate, observed_at=event.observed_at)

    # --- internals --------------------------------------------------------

    def _destination_from_route(self, route_signature: str) -> str:
        """Extract the rightmost airport code from a route signature.

        Accepts both 'BWI->BOG direct' and 'BWI->MIA->BOG' shapes; falls
        back to 'BOG' if parsing fails (Colombia-only desk default).
        """
        if not route_signature:
            return "BOG"
        tail = route_signature.split("->")[-1].strip()
        # strip a trailing ' direct' or ' positioning' qualifier
        code = tail.split()[0] if tail else ""
        return code.upper() if code else "BOG"

    def _to_report(
        self,
        event: AlertEvent,
        estimate: PairingEstimate,
        *,
        observed_at: datetime,
    ) -> SpecialistReport:
        best = estimate.best_option
        priced_count = sum(
            1 for o in estimate.options if o.round_trip_total_usd is not None
        )
        total_count = len(estimate.options)

        if priced_count == 0:
            status = Status.NO_DATA
            confidence = 0.0
        elif priced_count < total_count:
            status = Status.PARTIAL
            confidence = priced_count / total_count
        else:
            # Layer 3: even fully-priced placeholder data is a stub —
            # mark it so Oak Street can label it as foundation-stage.
            status = Status.STUB
            confidence = 0.6  # placeholder, not live

        payload = {
            "origin": estimate.origin,
            "destination": estimate.destination,
            "outbound_depart": estimate.outbound_depart.isoformat(),
            "outbound_price_usd": estimate.outbound_price_usd,
            "options": [
                {
                    "window_days": o.window_days,
                    "return_date": o.return_date.isoformat(),
                    "return_price_usd": o.return_price_usd,
                    "round_trip_total_usd": o.round_trip_total_usd,
                    "confidence": o.confidence,
                }
                for o in estimate.options
            ],
        }
        flags: list[str] = []
        if status is Status.STUB:
            flags.append("placeholder-fetcher")
        if priced_count < total_count and priced_count > 0:
            flags.append("partial-window-coverage")

        verdict_input: dict = {}
        if best is not None:
            verdict_input["round_trip_est_usd"] = best.round_trip_total_usd
            verdict_input["best_return_window_days"] = best.window_days

        log.info(
            "Delta report deal=%s status=%s priced=%d/%d best=%s",
            event.deal_id, status.value, priced_count, total_count,
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
