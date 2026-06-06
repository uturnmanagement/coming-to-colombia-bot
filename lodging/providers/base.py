"""Lodging provider interface (Phase 6A).

Mirrors the Layer-4 `intel/lodging/providers/interface.py` philosophy:
a provider returns a `ProviderResult` wrapping a status flag so the
engine knows whether to use the data or fall through. Providers NEVER
raise — failure is reported via `status=ERROR`.

Phase 6A ships exactly one usable provider (`mock`). The live providers
(Booking.com, Hostelworld, Airbnb) are present as STUBs so the
architecture is ready, but they perform NO network I/O and return
`status=STUB` until a later phase supplies a real transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from lodging.lodging_models import NightlyQuote


class ProviderStatus(str, Enum):
    OK = "ok"          # quotes returned, usable
    EMPTY = "empty"    # provider reachable, no data for the city
    STUB = "stub"      # provider intentionally inactive (Phase 6A)
    ERROR = "error"    # provider failed


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderStatus
    quotes: tuple[NightlyQuote, ...] = ()
    reason: str = ""
    source: str = ""

    @property
    def is_usable(self) -> bool:
        return self.status is ProviderStatus.OK and bool(self.quotes)


@runtime_checkable
class LodgingProvider(Protocol):
    """Every provider exposes the same shape.

    `name` is a short stable identifier persisted into quotes.
    `is_live` is False for mock/stub providers and only True once a real
    transport is wired. `fetch_city` runs one query and returns a
    ProviderResult — it never raises.
    """

    name: str
    is_live: bool

    def fetch_city(self, city: str) -> ProviderResult: ...
