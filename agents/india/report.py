"""India — typed data shapes.

Internal vocabulary:

    AccommodationCategory   Hostel Dorm | Hostel Private Room |
                            Budget Hotel | Guest House
    HostelOption            one accommodation candidate, optionally
                            carrying its ScoreBreakdown after India
                            has scored it
    HostelSignal            compact roll-up of India's recommendation
                            (the equivalent of LodgingSignal at the
                            hostel layer)
    HostelReport            India's full internal report — options +
                            chosen signal + cached lodging context
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class AccommodationCategory(str, Enum):
    HOSTEL_DORM = "hostel_dorm"
    HOSTEL_PRIVATE_ROOM = "hostel_private_room"
    BUDGET_HOTEL = "budget_hotel"
    GUEST_HOUSE = "guest_house"


@dataclass(frozen=True)
class HostelOption:
    name: str
    category: AccommodationCategory
    city: str
    neighborhood: Optional[str]
    price_usd: float
    distance_to_center_km: float
    source: str                                # provider name
    listing_ref: Optional[str] = None
    score_breakdown: Optional["ScoreBreakdown"] = None  # filled by India


@dataclass(frozen=True)
class HostelSignal:
    """Compact roll-up India will hand to Oak Street via verdict_input.

    Mirrors the Layer 4 LodgingSignal shape philosophy: only the
    fields the briefing actually needs.
    """
    city: str
    best_option_name: str
    best_category: AccommodationCategory
    best_price_usd: float
    best_score: float                  # 0..100 — overall recommendation
    options_count: int
    observed_at: datetime
    season_code: Optional[str]         # e.g. "low" / "peak" / None
    lodging_color: Optional[str]       # e.g. "red" / None


@dataclass(frozen=True)
class HostelReport:
    """India's internal report. Wrapped into SpecialistReport.payload."""
    city: str
    observed_at: datetime
    options: tuple[HostelOption, ...]
    signal: Optional[HostelSignal]
    on_date: date
    flags: tuple[str, ...] = field(default_factory=tuple)


# Avoid a circular import by forward-resolving the type hint above.
# We import ScoreBreakdown lazily so report.py stays cheap to import.
def _resolve() -> None:
    from .scoring import ScoreBreakdown  # noqa: F401
