"""Delta — Return Pairing specialist.

Stage 2 upgrades Delta into a live return-flight optimizer:
    - Pure return-window math + pairing engine in intel/return_pairing.
    - Coloring + ranking in intel/return_pairing/ranking.
    - Specialist shell here takes an outbound observation and emits a
      SpecialistReport carrying full per-window itinerary detail.
    - Live fetching reuses the verified scanner LiveFlightFetcher, gated
      behind DELTA_LIVE_RETURNS (default off → offline placeholder).
"""
from .specialist import (
    Delta,
    make_live_return_fetcher,
    make_placeholder_offer_fetcher,
    placeholder_return_fetcher,
    sampled_return_days,
)
from .report import render_delta_report

__all__ = [
    "Delta",
    "make_live_return_fetcher",
    "make_placeholder_offer_fetcher",
    "placeholder_return_fetcher",
    "sampled_return_days",
    "render_delta_report",
]
