"""Live-provider foundation (Layer 7A).

A hermetic, gated substrate for live airfare/lodging data. No real HTTP
transport is wired by default and there is NO Telegram path here — this
package only produces typed data records. Activation requires explicit
opt-in (enable_live + key) AND a deliberately-supplied transport.
"""
from __future__ import annotations

from .airfare import AirfareQuote, LiveAirfareProvider, make_live_airfare_provider
from .base import (
    LiveProvider,
    LiveProviderConfig,
    LiveProviderStatus,
    LiveResult,
    ProviderTimeout,
    ProviderTransportError,
)
from .fixture_transport import (
    FIXTURE_API_KEY,
    FIXTURES_DIR,
    FixtureLodgingTransport,
    make_fixture_lodging_provider,
)
from .lodging import LodgingQuote, LiveLodgingProvider, make_live_lodging_provider
from .mock import make_mock_airfare_provider, make_mock_lodging_provider
from .selection import build_airfare_provider, build_lodging_provider
from .transport import InjectableTransport, not_wired_transport

__all__ = [
    "AirfareQuote",
    "LodgingQuote",
    "LiveProvider",
    "LiveProviderConfig",
    "LiveProviderStatus",
    "LiveResult",
    "ProviderTimeout",
    "ProviderTransportError",
    "LiveAirfareProvider",
    "LiveLodgingProvider",
    "make_live_airfare_provider",
    "make_live_lodging_provider",
    "make_mock_airfare_provider",
    "make_mock_lodging_provider",
    "make_fixture_lodging_provider",
    "FixtureLodgingTransport",
    "FIXTURES_DIR",
    "FIXTURE_API_KEY",
    "build_airfare_provider",
    "build_lodging_provider",
    "InjectableTransport",
    "not_wired_transport",
]
