"""LodgingIntelService — the brain Echo and India will plug into.

Responsibilities:
    1. Pull observations from one or more providers.
    2. Persist them to lodging_history.
    3. Compute the baseline and persist it to lodging_baseline.
    4. Score a single observed price against the baseline using the
       season-weighted classifier.
    5. Emit a LodgingSignal — the small, typed value that future Echo
       and India will drop into their `verdict_input["lodging_signal"]`
       slot.

The service makes no Telegram calls and never invokes the live
dispatcher. It is intentionally agnostic of Oak Street.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional, Sequence

from agents.logging_setup import get_logger
from .baseline import LodgingBaseline, compute_baseline
from .providers.interface import (
    LodgingObservation,
    LodgingProvider,
    ProviderResult,
    ProviderStatus,
)
from .scoring import (
    LodgingColor,
    LodgingScore,
    LodgingThresholds,
    score_observation,
)
from .seasons import Season
from .storage import LodgingStorage

log = get_logger("lodging")


@dataclass(frozen=True)
class LodgingSignal:
    """Compact summary intended for verdict_input['lodging_signal'].

    Includes only the fields Echo / India need to render — the full
    LodgingScore stays inside LodgingIntelService for audit.
    """
    color: LodgingColor
    weighted_pct_below: float
    raw_pct_below: float
    baseline_price_usd: float
    observed_price_usd: float
    season: Season
    sample_size: int
    on_date: date

    def as_verdict_dict(self) -> dict:
        """Compact, JSON-serializable projection for a specialist's
        ``verdict_input['lodging_signal']`` slot.

        The SpecialistReport contract requires every ``verdict_input``
        value to survive ``json.dumps`` (the schema is transported and
        audited as JSON). LodgingSignal itself carries enums and a
        ``date``, so consumers (Layer 6 Echo) drop in this dict instead
        of the dataclass.
        """
        return {
            "color": self.color.value,
            "weighted_pct_below": self.weighted_pct_below,
            "raw_pct_below": self.raw_pct_below,
            "baseline_price_usd": self.baseline_price_usd,
            "observed_price_usd": self.observed_price_usd,
            "season": self.season.value,
            "sample_size": self.sample_size,
            "on_date": self.on_date.isoformat(),
        }


@dataclass
class LodgingIntelService:
    """Orchestration shell for the lodging brain."""
    storage: LodgingStorage
    providers: Sequence[LodgingProvider]
    lookback_days: int = 90
    thresholds: LodgingThresholds = field(default_factory=LodgingThresholds)
    season_weighting: bool = True
    enabled: bool = True

    # --- ingestion --------------------------------------------------------

    def refresh_observations(
        self,
        *,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> list[ProviderResult]:
        """Pull from every provider and persist their observations.

        Returns the per-provider ProviderResult list so the caller (and
        tests) can inspect statuses. Always returns; never raises.
        """
        if not self.enabled:
            return []
        results: list[ProviderResult] = []
        for provider in self.providers:
            try:
                result = provider.fetch(
                    city=city, neighborhood=neighborhood, beds=beds,
                    lookback_days=self.lookback_days, now=now,
                )
            except Exception as exc:  # noqa: BLE001 — surface as ERROR
                log.exception("provider %s raised", provider.name)
                results.append(ProviderResult(
                    status=ProviderStatus.ERROR,
                    observations=(),
                    reason=f"{type(exc).__name__}: {exc}",
                    source=getattr(provider, "name", "?"),
                ))
                continue
            results.append(result)
            if result.is_usable:
                self.storage.record_observations(result.observations)
        return results

    def build_baseline(
        self,
        *,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        observations: Optional[Iterable[LodgingObservation]] = None,
        now: Optional[datetime] = None,
    ) -> Optional[LodgingBaseline]:
        """Compute and persist a baseline. If `observations` is None,
        the service re-reads from lodging_history."""
        if not self.enabled:
            return None
        when = now or datetime.now()
        obs_list = list(observations) if observations is not None else \
            self._history_as_observations(city, neighborhood, beds)
        baseline = compute_baseline(
            obs_list,
            lookback_days=self.lookback_days,
            now=when,
            city=city,
            neighborhood=neighborhood,
            beds=beds,
        )
        if baseline is None:
            return None
        self.storage.save_baseline(baseline)
        return baseline

    # --- scoring path -----------------------------------------------------

    def signal_for(
        self,
        *,
        observed_usd: float,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        on_date: Optional[date] = None,
    ) -> Optional[LodgingSignal]:
        """Score one observed price against the latest stored baseline.

        Returns None when intel is disabled OR no baseline is on file
        for the (city, neighborhood, beds) tuple yet — the caller
        (future Echo / India) treats `None` the same as
        "lodging_signal=None" today.
        """
        if not self.enabled:
            return None
        row = self.storage.latest_baseline(
            city, neighborhood=neighborhood, beds=beds,
        )
        if row is None:
            return None
        on = on_date or date.today()
        score = score_observation(
            observed_usd=observed_usd,
            baseline_usd=float(row["baseline_price_usd"]),
            on_date=on,
            thresholds=self.thresholds,
            weighting_enabled=self.season_weighting,
        )
        return LodgingSignal(
            color=score.color,
            weighted_pct_below=score.weighted_pct_below,
            raw_pct_below=score.raw_pct_below,
            baseline_price_usd=score.baseline_usd,
            observed_price_usd=score.observed_usd,
            season=score.season,
            sample_size=int(row["sample_size"]),
            on_date=on,
        )

    # --- internals --------------------------------------------------------

    def _history_as_observations(
        self,
        city: str,
        neighborhood: Optional[str],
        beds: Optional[int],
    ) -> list[LodgingObservation]:
        rows = self.storage.history_for(
            city, neighborhood=neighborhood, beds=beds,
        )
        obs: list[LodgingObservation] = []
        for row in rows:
            obs.append(LodgingObservation(
                city=row["city"],
                neighborhood=row["neighborhood"],
                beds=row["beds"],
                observed_at=datetime.fromisoformat(row["observed_at"]),
                stay_date=date.fromisoformat(row["stay_date"]),
                price_usd=float(row["price_usd"]),
                source=row["source"],
                listing_ref=row["listing_ref"],
            ))
        return obs
