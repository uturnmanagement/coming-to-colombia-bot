"""Live airfare provider — normalizes a raw quote payload.

The expected raw shape (provider-agnostic; a real adapter's transport
would translate a vendor response into this before returning it):

    {"quotes": [
        {"origin": "BWI", "destination": "BOG",
         "price_usd": 285.0, "depart_date": "2026-06-01",
         "carrier": "AV"},
        ...
    ]}

``_parse`` raises on any shape/type problem so the base maps it to
MALFORMED; an empty ``quotes`` list yields EMPTY via the base.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import LiveProvider, LiveProviderConfig


@dataclass(frozen=True)
class AirfareQuote:
    origin: str
    destination: str
    price_usd: float
    depart_date: str
    carrier: str = ""


@dataclass
class LiveAirfareProvider(LiveProvider):
    name: str = "live_airfare"

    def _build_request(self, **query) -> dict:
        # A real adapter would attach auth headers / map params here.
        return {"params": dict(query), "api_key": self.config.api_key}

    def _parse(self, raw: Any) -> tuple:
        quotes = raw["quotes"]  # KeyError -> MALFORMED
        if not isinstance(quotes, list):
            raise TypeError("'quotes' must be a list")
        out = []
        for q in quotes:
            out.append(AirfareQuote(
                origin=str(q["origin"]).upper(),
                destination=str(q["destination"]).upper(),
                price_usd=float(q["price_usd"]),
                depart_date=str(q["depart_date"]),
                carrier=str(q.get("carrier", "")),
            ))
        return tuple(out)


def make_live_airfare_provider(
    *, enable_live: bool, api_key: str, timeout_seconds: float = 8.0,
    transport=None,
) -> LiveAirfareProvider:
    return LiveAirfareProvider(
        config=LiveProviderConfig(
            provider_name="live_airfare",
            enable_live=enable_live,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        ),
        transport=transport,
    )
