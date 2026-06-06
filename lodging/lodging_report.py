"""Lodging report — public rendering entry points (Phase 6A).

Thin facade over the engine + summary renderer. Two uses:

1. `render_delta_lodging_appendix(destination_code)` — the block the
   Delta Return Optimizer report appends for a destination city. Returns
   "" for any code outside the supported desk cities (the 15-city
   Colombia registry, lodging_models.CITY_REGISTRY) so the flight
   report degrades cleanly.
2. `render_all_cities()` — a standalone Lodging Summary across all
   supported cities, for demos / manual review.

This module performs NO network I/O and touches no flight, return,
heartbeat, or Telegram logic.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from lodging.lodging_engine import LodgingEngine
from lodging.reports.summary import render_city_summary

_HEADER = "LODGING INTELLIGENCE APPENDIX (Phase 6A — mock data)"


def render_delta_lodging_appendix(
    destination_code: Optional[str], *, now: Optional[datetime] = None
) -> str:
    """Render the lodging block for a Delta report's destination city.

    Returns an empty string when the destination is not one of the
    supported desk cities (the 15-city Colombia registry — see
    lodging_models.CITY_REGISTRY).
    """
    engine = LodgingEngine()
    summary = engine.summarize_for_code(destination_code, now=now)
    if summary is None or not summary.estimates:
        return ""
    return render_city_summary(summary)


def render_all_cities(*, now: Optional[datetime] = None) -> str:
    """Standalone Lodging Summary across all supported cities (the
    15-city Colombia registry)."""
    engine = LodgingEngine()
    blocks = [_HEADER, ""]
    for summary in engine.summarize_all(now=now):
        blocks.append(render_city_summary(summary).rstrip())
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"
