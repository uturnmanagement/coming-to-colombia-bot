"""Provider interface — what every lodging data source must look like.

LodgingObservation is the unit. LodgingProvider is the protocol.
ProviderResult wraps a fetch with a status flag so the orchestrating
service knows whether to use the data or fall through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


class ProviderStatus(str, Enum):
    OK = "ok"                # observations returned
    EMPTY = "empty"          # provider reachable, no data for the query
    STUB = "stub"            # provider is intentionally inactive (Layer 4)
    ERROR = "error"          # provider failed


@dataclass(frozen=True)
class LodgingObservation:
    """One nightly lodging price observation."""
    city: str
    neighborhood: Optional[str]
    beds: Optional[int]
    observed_at: datetime           # when WE observed the listing
    stay_date: date                 # the night the price was offered for
    price_usd: float
    source: str                     # provider name (e.g. "mock" | "airdna")
    listing_ref: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderStatus
    observations: tuple[LodgingObservation, ...]
    reason: str = ""
    source: str = ""

    @property
    def is_usable(self) -> bool:
        return self.status is ProviderStatus.OK and bool(self.observations)


@runtime_checkable
class LodgingProvider(Protocol):
    """Every provider exposes the same shape.

    `name` is a short stable identifier persisted into observations.
    `fetch` runs one query and returns a ProviderResult — never raises;
    failure is reported via `status=ERROR`.
    """
    name: str

    def fetch(
        self,
        *,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        lookback_days: int = 90,
        now: Optional[datetime] = None,
    ) -> ProviderResult:
        ...
