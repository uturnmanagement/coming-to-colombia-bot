"""Live lodging provider — normalizes a raw listing payload.

Expected raw shape (provider-agnostic):

    {"listings": [
        {"city": "BOG", "price_usd": 22.0, "beds": 1,
         "neighborhood": "La Candelaria", "stay_date": "2026-06-01",
         "listing_ref": "abc123"},
        ...
    ]}

``_parse`` raises on any shape/type problem (-> MALFORMED); an empty
``listings`` list yields EMPTY. The normalized ``LodgingQuote`` is a
small, transport-neutral record; bridging it to the Layer 4
``LodgingObservation`` / ``LodgingProvider`` protocol is deferred to the
Oak Street integration layer (7B) and intentionally not done here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .base import LiveProvider, LiveProviderConfig


@dataclass(frozen=True)
class LodgingQuote:
    city: str
    price_usd: float
    beds: Optional[int] = None
    neighborhood: Optional[str] = None
    stay_date: Optional[str] = None
    listing_ref: Optional[str] = None


@dataclass
class LiveLodgingProvider(LiveProvider):
    name: str = "live_lodging"

    def _build_request(self, **query) -> dict:
        return {"params": dict(query), "api_key": self.config.api_key}

    def _parse(self, raw: Any) -> tuple:
        listings = raw["listings"]  # KeyError -> MALFORMED
        if not isinstance(listings, list):
            raise TypeError("'listings' must be a list")
        out = []
        for item in listings:
            beds = item.get("beds")
            out.append(LodgingQuote(
                city=str(item["city"]).upper(),
                price_usd=float(item["price_usd"]),
                beds=None if beds is None else int(beds),
                neighborhood=item.get("neighborhood"),
                stay_date=item.get("stay_date"),
                listing_ref=item.get("listing_ref"),
            ))
        return tuple(out)


def make_live_lodging_provider(
    *, enable_live: bool, api_key: str, timeout_seconds: float = 8.0,
    transport=None,
) -> LiveLodgingProvider:
    return LiveLodgingProvider(
        config=LiveProviderConfig(
            provider_name="live_lodging",
            enable_live=enable_live,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        ),
        transport=transport,
    )
