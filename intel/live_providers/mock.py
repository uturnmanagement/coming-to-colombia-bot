"""Mock live providers — deterministic, hermetic, no external API.

These exercise the *entire* LiveProvider pipeline (gating, transport,
parse) but with a deterministic in-process transport, so "mock provider
mode" yields stable OK results offline. They are the default selection
(see ``selection.py``) and the safe local-testing posture.
"""
from __future__ import annotations

from typing import Any

from .airfare import LiveAirfareProvider
from .base import LiveProviderConfig
from .lodging import LiveLodgingProvider


def mock_airfare_transport(*, timeout: float = 8.0, params: dict = None,
                           api_key: str = "", **_) -> Any:
    """Deterministic raw airfare payload derived from the query."""
    params = params or {}
    origin = str(params.get("origin", "BWI")).upper()
    dest = str(params.get("destination", "BOG")).upper()
    depart = str(params.get("depart_date", "2026-06-01"))
    return {"quotes": [
        {"origin": origin, "destination": dest,
         "price_usd": 285.0, "depart_date": depart, "carrier": "AV"},
        {"origin": origin, "destination": dest,
         "price_usd": 312.0, "depart_date": depart, "carrier": "CM"},
    ]}


def mock_lodging_transport(*, timeout: float = 8.0, params: dict = None,
                           api_key: str = "", **_) -> Any:
    """Deterministic raw lodging payload derived from the query."""
    params = params or {}
    city = str(params.get("city", "BOG")).upper()
    return {"listings": [
        {"city": city, "price_usd": 22.0, "beds": 1,
         "neighborhood": "La Candelaria", "stay_date": "2026-06-01",
         "listing_ref": f"mock-{city}-1"},
        {"city": city, "price_usd": 31.0, "beds": 2,
         "neighborhood": "Chapinero", "stay_date": "2026-06-01",
         "listing_ref": f"mock-{city}-2"},
    ]}


def make_mock_airfare_provider() -> LiveAirfareProvider:
    return LiveAirfareProvider(
        config=LiveProviderConfig(
            provider_name="mock", enable_live=True, api_key="mock",
        ),
        transport=mock_airfare_transport,
        name="mock_airfare",
    )


def make_mock_lodging_provider() -> LiveLodgingProvider:
    return LiveLodgingProvider(
        config=LiveProviderConfig(
            provider_name="mock", enable_live=True, api_key="mock",
        ),
        transport=mock_lodging_transport,
        name="mock_lodging",
    )
