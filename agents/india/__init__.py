"""India — hostel & budget-accommodation specialist.

Layer 5 ships India as a foundation that:
    - consumes the same AlertEvent every other specialist sees
    - pulls accommodation options via a provider (mock only in
      Layer 5; no HTTP, no scraping, no third-party API)
    - consults the Layer 4 LodgingIntelService for a city-wide
      lodging signal (color + season) when one is available
    - scores each option on four axes (price, location, season,
      lodging_signal) and an overall recommendation
    - emits a HostelReport internally plus a SpecialistReport for
      Oak Street's typed ingestion path
"""
from .report import (
    AccommodationCategory,
    HostelOption,
    HostelReport,
    HostelSignal,
)
from .scoring import (
    SCORE_WEIGHTS,
    ScoreBreakdown,
    TYPICAL_PRICE_USD_BY_CATEGORY,
    score_lodging_signal,
    score_location,
    score_option,
    score_price,
    score_season,
)
from .providers import MockHostelProvider
from .specialist import India

__all__ = [
    "AccommodationCategory",
    "HostelOption",
    "HostelReport",
    "HostelSignal",
    "SCORE_WEIGHTS",
    "ScoreBreakdown",
    "TYPICAL_PRICE_USD_BY_CATEGORY",
    "score_lodging_signal",
    "score_location",
    "score_option",
    "score_price",
    "score_season",
    "MockHostelProvider",
    "India",
]
