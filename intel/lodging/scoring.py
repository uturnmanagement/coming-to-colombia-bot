"""RED/YELLOW/GREEN scoring for an observed lodging price.

Thresholds (per Colombia Desk builder spec):
    GREEN   < 8%  below typical (weighted)
    YELLOW  8% – 14.99% below typical (weighted)
    RED     >= 15% below typical (weighted)

Weighting:
    weighted_pct = raw_pct * season_multiplier

Where raw_pct = (baseline - observed) / baseline * 100.

The same dataclasses ride through to LodgingIntelService and into
Echo's `lodging_signal` slot (reserved in Layer 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from .seasons import Season, classify_season, season_multiplier


class LodgingColor(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class LodgingThresholds:
    """Cut-points for color classification, in pct-below-baseline."""
    yellow_pct: float = 8.0    # YELLOW when weighted_pct >= yellow_pct
    red_pct: float = 15.0      # RED    when weighted_pct >= red_pct

    def __post_init__(self) -> None:
        if not 0 < self.yellow_pct < self.red_pct:
            raise ValueError(
                f"thresholds must satisfy 0 < yellow ({self.yellow_pct}) "
                f"< red ({self.red_pct})"
            )


@dataclass(frozen=True)
class LodgingScore:
    color: LodgingColor
    raw_pct_below: float           # (baseline - observed) / baseline * 100
    weighted_pct_below: float      # raw * season_multiplier
    season: Season
    season_multiplier_applied: float
    weighting_enabled: bool
    baseline_usd: float
    observed_usd: float
    on_date: date
    thresholds: LodgingThresholds


def score_observation(
    *,
    observed_usd: float,
    baseline_usd: float,
    on_date: date,
    thresholds: Optional[LodgingThresholds] = None,
    weighting_enabled: bool = True,
) -> LodgingScore:
    """Classify an observed lodging price against the baseline.

    `weighting_enabled=False` collapses the multiplier to 1.0 so the
    raw pct alone drives the color — useful when the operator wants
    a season-agnostic view (and for the LODGING_SEASON_WEIGHTING env
    knob).
    """
    if baseline_usd <= 0:
        raise ValueError(
            f"baseline_usd must be > 0 to score, got {baseline_usd}"
        )
    if observed_usd < 0:
        raise ValueError(f"observed_usd must be >= 0, got {observed_usd}")

    th = thresholds or LodgingThresholds()
    raw_pct = (baseline_usd - observed_usd) / baseline_usd * 100.0

    season = classify_season(on_date)
    multiplier = season_multiplier(on_date) if weighting_enabled else 1.0
    weighted_pct = raw_pct * multiplier

    if weighted_pct >= th.red_pct:
        color = LodgingColor.RED
    elif weighted_pct >= th.yellow_pct:
        color = LodgingColor.YELLOW
    else:
        color = LodgingColor.GREEN

    return LodgingScore(
        color=color,
        raw_pct_below=round(raw_pct, 4),
        weighted_pct_below=round(weighted_pct, 4),
        season=season,
        season_multiplier_applied=multiplier,
        weighting_enabled=weighting_enabled,
        baseline_usd=round(baseline_usd, 2),
        observed_usd=round(observed_usd, 2),
        on_date=on_date,
        thresholds=th,
    )
