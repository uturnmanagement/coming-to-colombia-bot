"""Lodging Price Intelligence — shared brain Echo and India will use.

Pure intel modules:
    seasons.py      season classification + multiplier matrix (incl. Holy Week)
    scoring.py      RED/YELLOW/GREEN classifier (season-weighted)
    baseline.py     baseline aggregation from observation history
    storage.py      SQLite wrapper for lodging_baseline + lodging_history
    service.py      LodgingIntelService — orchestration shell

Provider adapters live under providers/. AirDNA and Inside Airbnb
ship as `STUB` adapters in Layer 4 — no HTTP, no file access. The
deterministic MockLodgingProvider drives every test.
"""
from .seasons import (
    HOLY_WEEK_DAYS,
    Season,
    SEASON_MULTIPLIERS,
    classify_season,
    gauss_easter,
    holy_week,
    season_multiplier,
)
from .scoring import (
    LodgingColor,
    LodgingScore,
    LodgingThresholds,
    score_observation,
)
from .baseline import LodgingBaseline, compute_baseline
from .storage import LodgingStorage
from .service import LodgingIntelService, LodgingSignal

__all__ = [
    "HOLY_WEEK_DAYS",
    "Season",
    "SEASON_MULTIPLIERS",
    "classify_season",
    "gauss_easter",
    "holy_week",
    "season_multiplier",
    "LodgingColor",
    "LodgingScore",
    "LodgingThresholds",
    "score_observation",
    "LodgingBaseline",
    "compute_baseline",
    "LodgingStorage",
    "LodgingIntelService",
    "LodgingSignal",
]
