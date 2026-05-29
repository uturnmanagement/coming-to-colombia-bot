"""SpecialistReport — the shared contract every Colombia Desk specialist
hands to Oak Street.

Layer 3 introduces two specialists:

  - Delta  → return-pairing estimates
  - Echo   → price-context classification (lodging hook reserved)

Both produce a `SpecialistReport`. Oak Street's `ingest_report(...)` is
the only caller that turns these into an internal briefing or a live
Telegram render. By keeping the schema typed and frozen, future
specialists (India, Juliet, ...) can be added without renegotiating
the wire format and without changing Oak Street's dispatcher contract.

Vocabulary chosen here is meant to be load-bearing across layers — do
not redefine `Status` or `verdict_input` shapes inside specialists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class Status(str, Enum):
    """Coarse outcome of a specialist run.

    The Status alone tells Oak Street whether to use the report or
    skip it. Confidence and flags carry the nuance.
    """
    OK = "ok"                # Data flowed end-to-end.
    PARTIAL = "partial"      # Some data; degraded. Use with caution.
    NO_DATA = "no_data"      # Source returned empty.
    STUB = "stub"            # Specialist intentionally not live yet
                             # (Echo until lodging hook is wired,
                             # Delta until live return-leg fetch).
    ERROR = "error"          # The specialist failed.


# Verdict-input vocabulary is intentionally small. Each key is a hint
# Oak Street uses to decide colorings, headlines, and ordering. Add
# new keys only when a specialist needs one — never repurpose.
VERDICT_KEYS = {
    "round_trip_est_usd",      # Delta
    "best_return_window_days", # Delta
    "price_position_label",    # Echo  (e.g. "great", "good", "normal")
    "price_position_pct",      # Echo  (0..100; lower = cheaper)
    "lodging_signal",          # Echo  (reserved — None in Layer 3)
    # --- Layer 5: India (hostel + budget accommodation) ---
    "best_hostel_score",       # India (0..100; higher = better)
    "best_hostel_category",    # India (AccommodationCategory.value)
    "best_hostel_price_usd",   # India (USD/night)
    "hostel_options_count",    # India (int — total options considered)
}


@dataclass(frozen=True)
class SpecialistReport:
    agent: str                   # e.g. "delta" | "echo"
    status: Status
    confidence: float            # 0.0..1.0
    deal_id: Optional[str]
    observed_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    flags: tuple[str, ...] = ()
    verdict_input: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Cheap invariants — catch contract drift early.
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence {self.confidence} outside [0,1] (agent={self.agent})"
            )
        unknown = set(self.verdict_input) - VERDICT_KEYS
        if unknown:
            raise ValueError(
                f"verdict_input keys unknown: {sorted(unknown)}; "
                f"extend agents.specialist_report.VERDICT_KEYS before use"
            )

    def to_json(self) -> str:
        """Stable JSON form for storage / audit / cross-process transport."""
        data = asdict(self)
        data["status"] = self.status.value
        data["observed_at"] = self.observed_at.isoformat()
        return json.dumps(data, default=str, separators=(",", ":"))
