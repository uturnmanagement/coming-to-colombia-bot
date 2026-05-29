"""Lodging data-source providers.

Layer 4 ships:
    interface.py        LodgingObservation dataclass + LodgingProvider protocol
    mock.py             MockLodgingProvider — deterministic, drives every test
    airdna.py           AirDnaProvider — stub. No HTTP.
    inside_airbnb.py    InsideAirbnbProvider — stub. No filesystem read.

Live HTTP / file ingestion is explicitly deferred. Both real providers
return `ProviderResult(status='stub', ...)` so the surrounding service
can be exercised without surprises.
"""
from .interface import (
    LodgingObservation,
    LodgingProvider,
    ProviderResult,
    ProviderStatus,
)
from .mock import MockLodgingProvider
from .airdna import AirDnaProvider
from .inside_airbnb import InsideAirbnbProvider

__all__ = [
    "LodgingObservation",
    "LodgingProvider",
    "ProviderResult",
    "ProviderStatus",
    "MockLodgingProvider",
    "AirDnaProvider",
    "InsideAirbnbProvider",
]
