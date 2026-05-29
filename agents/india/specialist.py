"""India — hostel & budget-accommodation specialist shell.

Consumes an outbound AlertEvent; calls the mock hostel provider for
candidate options; consults the Layer 4 LodgingIntelService when one
is wired; scores every option; and emits a SpecialistReport whose
payload is the typed HostelReport.

DRY_RUN-safe: this specialist never sends anywhere. Oak Street is the
only place that decides whether the report is surfaced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from agents.logging_setup import get_logger
from agents.oakstreet.orchestrator import AlertEvent
from agents.specialist_report import SpecialistReport, Status
from intel.lodging.scoring import LodgingColor
from intel.lodging.seasons import classify_season

from .providers import HostelProvider, MockHostelProvider
from .report import (
    AccommodationCategory,
    HostelOption,
    HostelReport,
    HostelSignal,
)
from .scoring import ScoreBreakdown, score_option

log = get_logger("india")


@dataclass
class India:
    """India specialist — hostel & budget accommodation intelligence."""
    provider: HostelProvider = field(default_factory=MockHostelProvider)
    # Optional injection of the Layer 4 lodging brain. India is fully
    # functional without it (lodging_signal=None just neutralizes the
    # corresponding sub-score); when present, India consults it for
    # the city-wide lodging color.
    lodging_service: Optional[object] = None
    # Per-category typical-price override; None uses the module defaults.
    typical_prices: Optional[dict[AccommodationCategory, float]] = None

    def analyze(
        self,
        event: AlertEvent,
        *,
        city: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> SpecialistReport:
        observed_at = event.observed_at if not now else now
        target_city = (city or self._destination_from_route(event.route_signature))
        options_raw = self.provider.fetch(city=target_city, now=observed_at)

        on_date = observed_at.date()
        season = classify_season(on_date)
        lodging_color = self._consult_lodging(target_city, on_date)

        scored: list[HostelOption] = []
        for opt in options_raw:
            breakdown = score_option(
                observed_usd=opt.price_usd,
                category=opt.category,
                distance_to_center_km=opt.distance_to_center_km,
                season=season,
                lodging_color=lodging_color,
                typical_table=self.typical_prices,
            )
            # HostelOption is frozen — re-emit with score_breakdown set.
            scored.append(HostelOption(
                name=opt.name, category=opt.category, city=opt.city,
                neighborhood=opt.neighborhood, price_usd=opt.price_usd,
                distance_to_center_km=opt.distance_to_center_km,
                source=opt.source, listing_ref=opt.listing_ref,
                score_breakdown=breakdown,
            ))

        signal = self._build_signal(
            city=target_city, options=tuple(scored),
            observed_at=observed_at, season_code=season.value,
            lodging_color_value=lodging_color.value if lodging_color else None,
        )
        report = HostelReport(
            city=target_city,
            observed_at=observed_at,
            options=tuple(scored),
            signal=signal,
            on_date=on_date,
            flags=self._flags(scored, lodging_color),
        )
        return self._to_specialist_report(event, report, observed_at)

    # --- internals --------------------------------------------------------

    def _destination_from_route(self, route_signature: str) -> str:
        if not route_signature:
            return "BOG"
        tail = route_signature.split("->")[-1].strip()
        code = tail.split()[0] if tail else ""
        return code.upper() if code else "BOG"

    def _consult_lodging(
        self, city: str, on_date: date
    ) -> Optional[LodgingColor]:
        if self.lodging_service is None:
            return None
        try:
            sig = self.lodging_service.signal_for(
                observed_usd=self._proxy_observed_for_signal(city),
                city=city,
                on_date=on_date,
            )
        except Exception:  # noqa: BLE001 — degrade quietly
            log.exception("lodging_service.signal_for raised")
            return None
        return sig.color if sig is not None else None

    def _proxy_observed_for_signal(self, city: str) -> float:
        """India needs a number to call LodgingIntelService.signal_for(...)
        but the score itself does not depend on the observed-price input.

        We hand in the cheapest mock option's price as a stand-in so the
        service produces a deterministic signal during tests; in a live
        layer this becomes the median observed from the active scan.
        """
        opts = self.provider.fetch(city=city)
        prices = [o.price_usd for o in opts]
        return min(prices) if prices else 0.0

    def _build_signal(
        self,
        *,
        city: str,
        options: tuple[HostelOption, ...],
        observed_at: datetime,
        season_code: str,
        lodging_color_value: Optional[str],
    ) -> Optional[HostelSignal]:
        if not options:
            return None
        best = max(options, key=lambda o: o.score_breakdown.overall)
        return HostelSignal(
            city=city,
            best_option_name=best.name,
            best_category=best.category,
            best_price_usd=best.price_usd,
            best_score=best.score_breakdown.overall,
            options_count=len(options),
            observed_at=observed_at,
            season_code=season_code,
            lodging_color=lodging_color_value,
        )

    def _flags(
        self,
        options: tuple[HostelOption, ...],
        lodging_color: Optional[LodgingColor],
    ) -> tuple[str, ...]:
        flags = ["mock-provider"]
        if not options:
            flags.append("no-options-for-city")
        if lodging_color is None:
            flags.append("lodging-signal-unavailable")
        return tuple(flags)

    def _to_specialist_report(
        self,
        event: AlertEvent,
        report: HostelReport,
        observed_at: datetime,
    ) -> SpecialistReport:
        if not report.options:
            status = Status.NO_DATA
            confidence = 0.0
        elif "lodging-signal-unavailable" in report.flags:
            # The mock provider data is real and scored; only the
            # cross-layer lodging context is missing.
            status = Status.PARTIAL
            confidence = 0.5
        else:
            # Layer 5 stays a STUB-equivalent because the provider is
            # mock-only — even fully-scored, we are not yet on live data.
            status = Status.STUB
            confidence = 0.6

        # Build serialization-friendly payload.
        payload = {
            "city": report.city,
            "observed_at": observed_at.isoformat(),
            "on_date": report.on_date.isoformat(),
            "options": [
                {
                    "name": o.name,
                    "category": o.category.value,
                    "neighborhood": o.neighborhood,
                    "price_usd": o.price_usd,
                    "distance_to_center_km": o.distance_to_center_km,
                    "source": o.source,
                    "listing_ref": o.listing_ref,
                    "score": (None if o.score_breakdown is None else {
                        "price": o.score_breakdown.price,
                        "location": o.score_breakdown.location,
                        "season": o.score_breakdown.season,
                        "lodging_signal": o.score_breakdown.lodging_signal,
                        "overall": o.score_breakdown.overall,
                    }),
                }
                for o in report.options
            ],
            "signal": None if report.signal is None else {
                "city": report.signal.city,
                "best_option_name": report.signal.best_option_name,
                "best_category": report.signal.best_category.value,
                "best_price_usd": report.signal.best_price_usd,
                "best_score": report.signal.best_score,
                "options_count": report.signal.options_count,
                "season_code": report.signal.season_code,
                "lodging_color": report.signal.lodging_color,
            },
        }

        verdict_input: dict = {}
        if report.signal is not None:
            verdict_input["best_hostel_score"] = report.signal.best_score
            verdict_input["best_hostel_category"] = report.signal.best_category.value
            verdict_input["best_hostel_price_usd"] = report.signal.best_price_usd
            verdict_input["hostel_options_count"] = report.signal.options_count

        log.info(
            "India report deal=%s city=%s options=%d best=%.1f",
            event.deal_id, report.city, len(report.options),
            report.signal.best_score if report.signal else -1,
        )
        return SpecialistReport(
            agent="india",
            status=status,
            confidence=confidence,
            deal_id=event.deal_id,
            observed_at=observed_at,
            payload=payload,
            flags=report.flags,
            verdict_input=verdict_input,
        )
