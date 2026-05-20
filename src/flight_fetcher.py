"""Flight data connectors and the normalized FlightOffer model.

Providers (FLIGHT_API_PROVIDER):
  placeholder         - deterministic mock data, zero API keys.
  rapidapi_skyscanner - RapidAPI Skyscanner Flights & Travel API (verified).
  amadeus             - Amadeus Self-Service API.

The live connectors are origin/region agnostic — they take airport codes
and dates. The placeholder is driven by the active region pack. Every
live provider degrades gracefully: a missing key or any API failure
falls back to placeholder data so the bot always keeps running.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import region

log = logging.getLogger("airfare.fetcher")


@dataclass
class FlightOffer:
    """A single normalized flight offer (one leg)."""

    origin: str
    destination: str
    price_usd: float
    depart_dt: datetime
    arrive_dt: datetime
    airline: str
    stops: int

    @property
    def duration_hours(self) -> float:
        return (self.arrive_dt - self.depart_dt).total_seconds() / 3600.0

    def as_dict(self) -> dict:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "price_usd": round(self.price_usd, 2),
            "depart": self.depart_dt.isoformat(),
            "arrive": self.arrive_dt.isoformat(),
            "airline": self.airline,
            "stops": self.stops,
            "duration_hours": round(self.duration_hours, 1),
        }


# --- placeholder fare model (region-driven) --------------------------------

_AIRLINES = ["Avianca", "American", "JetBlue", "Spirit", "Delta", "United", "Frontier"]


def _base_price(origin: str, destination: str) -> float:
    """Generic mock base fare, derived from the active region pack."""
    pack = region.active()
    if origin == pack.origin and pack.is_destination(destination):
        return pack.typical_price(destination)            # origin -> destination
    if origin == pack.origin:
        return 130.0                                      # origin -> gateway hop
    if pack.is_destination(destination):
        return pack.typical_price(destination) * 0.55     # gateway -> destination
    return 200.0


def _schedule(origin: str, destination: str) -> list[tuple[int, float]]:
    """Return (departure_hour, duration_hours) pairs for a route."""
    pack = region.active()
    if origin == pack.origin and pack.is_destination(destination):  # long-haul
        return [(7, 8.0), (11, 9.5), (16, 11.0)]
    if origin == pack.origin:  # short domestic hop
        return [(6, 2.4), (9, 2.6), (13, 2.3), (18, 2.7)]
    return [(8, 4.0), (12, 4.8), (16, 5.3), (20, 4.4)]  # gateway -> destination


class FlightFetcher:
    """Connector interface. Subclasses implement search()."""

    name = "base"

    def search(self, origin: str, destination: str, depart_day: date) -> list[FlightOffer]:
        raise NotImplementedError


class PlaceholderFlightFetcher(FlightFetcher):
    """Deterministic mock fetcher (seeded per route + date).

    Region-aware: prices follow the active region pack's typical fares.
    Used for keyless operation and as every live connector's fallback.
    """

    name = "placeholder"

    def __init__(self, seed: int | None = None):
        self._seed = seed

    def search(self, origin: str, destination: str, depart_day: date) -> list[FlightOffer]:
        origin, destination = origin.upper(), destination.upper()
        pack = region.active()
        seed = self._seed if self._seed is not None else 0
        rng = random.Random(f"{origin}-{destination}-{depart_day}-{seed}")
        base = _base_price(origin, destination)
        is_longhaul = origin == pack.origin and pack.is_destination(destination)
        offers: list[FlightOffer] = []
        for index, (hour, duration) in enumerate(_schedule(origin, destination)):
            price = base * rng.uniform(0.78, 1.30) + index * rng.uniform(-12, 22)
            price = max(45.0, round(price, 2))
            depart = datetime(
                depart_day.year, depart_day.month, depart_day.day,
                hour, rng.choice([0, 10, 25, 40, 55]),
            )
            arrive = depart + timedelta(hours=duration)
            offers.append(
                FlightOffer(
                    origin=origin,
                    destination=destination,
                    price_usd=price,
                    depart_dt=depart,
                    arrive_dt=arrive,
                    airline=rng.choice(_AIRLINES),
                    stops=1 if is_longhaul else 0,
                )
            )
        return offers


# --- Amadeus parsing helpers ------------------------------------------------

AMADEUS_TEST_BASE_URL = "https://test.api.amadeus.com"
_TOKEN_PATH = "/v1/security/oauth2/token"
_FLIGHT_OFFERS_PATH = "/v2/shopping/flight-offers"

_CARRIER_NAMES = {
    "AV": "Avianca", "AA": "American", "B6": "JetBlue", "NK": "Spirit",
    "DL": "Delta", "UA": "United", "F9": "Frontier", "CM": "Copa",
    "LA": "LATAM", "WN": "Southwest", "9E": "Endeavor", "BA": "British Airways",
}

# Providers routed through the live connector (caching + graceful fallback).
_LIVE_PROVIDERS = {"amadeus", "rapidapi_skyscanner"}

# RapidAPI Skyscanner Flights & Travel API endpoint paths.
RAPIDAPI_SEARCH_FLIGHTS_PATH = "/flights/searchFlights"
RAPIDAPI_SEARCH_AIRPORT_PATH = "/flights/searchAirport"


def _parse_amadeus_offer(raw: dict) -> FlightOffer | None:
    """Translate one Amadeus flight-offer object into a FlightOffer."""
    try:
        price_block = raw["price"]
        price = float(price_block.get("grandTotal") or price_block["total"])
        segments = raw["itineraries"][0]["segments"]
        first, last = segments[0], segments[-1]
        depart_dt = datetime.fromisoformat(first["departure"]["at"])
        arrive_dt = datetime.fromisoformat(last["arrival"]["at"])
        carrier = (
            (raw.get("validatingAirlineCodes") or [first.get("carrierCode", "")])[0]
        )
        return FlightOffer(
            origin=first["departure"]["iataCode"],
            destination=last["arrival"]["iataCode"],
            price_usd=round(price, 2),
            depart_dt=depart_dt,
            arrive_dt=arrive_dt,
            airline=_CARRIER_NAMES.get(carrier, carrier or "Unknown"),
            stops=len(segments) - 1,
        )
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _parse_skyscanner_itinerary(
    raw: dict, origin: str, destination: str
) -> FlightOffer | None:
    """Translate one Skyscanner itinerary into a FlightOffer.

    Verified against a live /flights/searchFlights response: an itinerary
    carries `price.amount` plus a one-way `legs[0]` with string `origin`/
    `destination`, ISO `departure`/`arrival`, `stopCount`, and a list of
    `carriers` ({name, logoUrl}). Returns None on any mismatch.
    """
    try:
        price = float(raw["price"]["amount"])
        leg = raw["legs"][0]
        depart_dt = datetime.fromisoformat(leg["departure"])
        arrive_dt = datetime.fromisoformat(leg["arrival"])
        carriers = leg.get("carriers") or []
        airline = carriers[0]["name"] if carriers else "Unknown"
        return FlightOffer(
            origin=str(leg.get("origin") or origin).upper(),
            destination=str(leg.get("destination") or destination).upper(),
            price_usd=round(price, 2),
            depart_dt=depart_dt,
            arrive_dt=arrive_dt,
            airline=airline,
            stops=int(leg.get("stopCount", 0)),
        )
    except (KeyError, IndexError, ValueError, TypeError):
        return None


class LiveFlightFetcher(FlightFetcher):
    """Live flight pricing connector (Amadeus + RapidAPI Skyscanner).

    Shared machinery: response caching (live quotas are small), a
    post-failure cooldown, and a graceful fallback to placeholder data on
    any failure. This connector is verified and operational — treat it as
    stable.
    """

    name = "live"

    FAILURE_COOLDOWN_SECONDS = 600
    CACHE_TTL_SECONDS = 2400  # 40 min
    # RapidAPI searchFlights is async server-side — retry when 'blocked'.
    RAPIDAPI_MAX_ATTEMPTS = 3
    RAPIDAPI_RETRY_SECONDS = 4

    def __init__(
        self,
        provider: str,
        api_key: str,
        api_secret: str = "",
        base_url: str = AMADEUS_TEST_BASE_URL,
        rapidapi_key: str = "",
        rapidapi_host: str = "",
    ):
        self.provider = provider
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.rapidapi_key = rapidapi_key
        self.rapidapi_host = rapidapi_host
        self._fallback = PlaceholderFlightFetcher()
        self._token: str | None = None
        self._token_expiry = 0.0
        self._cooldown_until = 0.0
        self._cache: dict[tuple, tuple[float, list[FlightOffer]]] = {}
        self._place_cache: dict[str, tuple[str, str]] = {}
        self._announced = False

    # --- public API ---------------------------------------------------------

    def search(self, origin: str, destination: str, depart_day: date) -> list[FlightOffer]:
        origin, destination = origin.upper(), destination.upper()
        if self.provider in _LIVE_PROVIDERS:
            return self._search_with_fallback(origin, destination, depart_day)
        dispatch = {
            "kiwi": self._search_kiwi,
            "skyscanner": self._search_skyscanner,
            "serpapi": self._search_serpapi,
        }
        handler = dispatch.get(self.provider)
        if handler is None:
            raise ValueError(f"Unknown FLIGHT_API_PROVIDER: {self.provider!r}")
        return handler(origin, destination, depart_day)

    def verify_connection(self) -> tuple[bool, str]:
        """Startup connectivity check. Returns (ok, human-readable message)."""
        if self.provider == "amadeus":
            try:
                self._get_token()
                return True, "Amadeus OAuth token acquired."
            except Exception as exc:  # noqa: BLE001
                return False, f"Amadeus connection failed: {exc}"
        if self.provider == "rapidapi_skyscanner":
            if not self.rapidapi_key:
                return False, "RapidAPI key missing"
            try:
                self._resolve_place(region.origin())
                return True, "RapidAPI Skyscanner reachable (airport lookup OK)."
            except Exception as exc:  # noqa: BLE001
                return False, f"RapidAPI Skyscanner connection failed: {exc}"
        return False, f"provider '{self.provider}' has no live connector yet"

    # --- live dispatch + shared fallback ------------------------------------

    def _search_live(
        self, origin: str, destination: str, depart_day: date
    ) -> list[FlightOffer]:
        if self.provider == "amadeus":
            return self._search_amadeus(origin, destination, depart_day)
        if self.provider == "rapidapi_skyscanner":
            return self._search_rapidapi_skyscanner(origin, destination, depart_day)
        raise ValueError(f"No live connector for provider {self.provider!r}")

    def _search_with_fallback(
        self, origin: str, destination: str, depart_day: date
    ) -> list[FlightOffer]:
        """Live search wrapped in caching + graceful placeholder fallback."""
        now = time.time()
        if now < self._cooldown_until:
            return self._fallback.search(origin, destination, depart_day)

        cache_key = (origin, destination, str(depart_day))
        cached = self._cache.get(cache_key)
        if cached is not None and now - cached[0] < self.CACHE_TTL_SECONDS:
            return cached[1]

        try:
            offers = self._search_live(origin, destination, depart_day)
        except Exception as exc:  # noqa: BLE001 - never let a scan crash
            log.warning(
                "%s search %s->%s %s failed (%s) - serving placeholder fallback",
                self.provider, origin, destination, depart_day, exc,
            )
            self._cooldown_until = now + self.FAILURE_COOLDOWN_SECONDS
            return self._fallback.search(origin, destination, depart_day)

        self._cache = {
            k: v for k, v in self._cache.items()
            if now - v[0] < self.CACHE_TTL_SECONDS
        }
        self._cache[cache_key] = (now, offers)
        return offers

    # --- Amadeus connector --------------------------------------------------

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        import requests  # lazy import

        resp = requests.post(
            self.base_url + _TOKEN_PATH,
            data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.api_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 1799))
        if not self._announced:
            log.info("LIVE AMADEUS API CONNECTED (%s)", self.base_url)
            self._announced = True
        return self._token

    def _search_amadeus(
        self, origin: str, destination: str, depart_day: date
    ) -> list[FlightOffer]:
        import requests  # lazy import

        token = self._get_token()
        resp = requests.get(
            self.base_url + _FLIGHT_OFFERS_PATH,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": depart_day.isoformat(),
                "adults": 1,
                "currencyCode": "USD",
                "max": 8,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", []) or []
        offers = [o for o in (_parse_amadeus_offer(r) for r in data) if o is not None]
        if not offers:
            log.info("Amadeus: no offers for %s->%s %s", origin, destination, depart_day)
        return offers

    # --- RapidAPI Skyscanner connector --------------------------------------

    def _rapidapi_headers(self) -> dict:
        return {
            "x-rapidapi-key": self.rapidapi_key,
            "x-rapidapi-host": self.rapidapi_host,
        }

    def _resolve_place(self, code: str) -> tuple[str, str]:
        """Resolve an airport code to its (skyId, entityId) via searchAirport."""
        code = code.upper()
        if code in self._place_cache:
            return self._place_cache[code]
        import requests  # lazy import

        resp = requests.get(
            f"https://{self.rapidapi_host}{RAPIDAPI_SEARCH_AIRPORT_PATH}",
            headers=self._rapidapi_headers(),
            params={"query": code},
            timeout=25,
        )
        resp.raise_for_status()
        places = resp.json().get("places", []) or []
        match = next(
            (p for p in places
             if p.get("placeType") == "AIRPORT"
             and str(p.get("skyId", "")).upper() == code),
            None,
        )
        if match is None:
            match = next(
                (p for p in places if p.get("placeType") == "AIRPORT"), None
            )
        if match is None and places:
            match = places[0]
        if match is None:
            raise ValueError(f"searchAirport returned no place for {code!r}")
        resolved = (str(match["skyId"]), str(match["entityId"]))
        self._place_cache[code] = resolved
        return resolved

    def _search_rapidapi_skyscanner(
        self, origin: str, destination: str, depart_day: date
    ) -> list[FlightOffer]:
        """RapidAPI Skyscanner connector — verified and operational.

        searchFlights is asynchronous server-side: an early call can
        return status 'blocked' with no results, so we retry a few times.
        """
        import requests  # lazy import

        origin_sky, origin_entity = self._resolve_place(origin)
        dest_sky, dest_entity = self._resolve_place(destination)
        url = f"https://{self.rapidapi_host}{RAPIDAPI_SEARCH_FLIGHTS_PATH}"
        params = {
            "originSkyId": origin_sky,
            "destinationSkyId": dest_sky,
            "originEntityId": origin_entity,
            "destinationEntityId": dest_entity,
            "date": depart_day.isoformat(),
            "adults": 1,
            "currency": "USD",
            "market": "US",
            "locale": "en-US",
            "cabinClass": "economy",
        }

        last_status = ""
        for attempt in range(self.RAPIDAPI_MAX_ATTEMPTS):
            resp = requests.get(
                url, headers=self._rapidapi_headers(), params=params, timeout=45
            )
            resp.raise_for_status()
            payload = resp.json()
            last_status = str(payload.get("status", ""))
            itineraries = payload.get("itineraries") or []
            if itineraries:
                offers = [
                    o for o in (
                        _parse_skyscanner_itinerary(it, origin, destination)
                        for it in itineraries
                    ) if o is not None
                ]
                if not offers:
                    log.info(
                        "RapidAPI: %d itineraries for %s->%s but none parsed.",
                        len(itineraries), origin, destination,
                    )
                return offers
            if attempt < self.RAPIDAPI_MAX_ATTEMPTS - 1:
                time.sleep(self.RAPIDAPI_RETRY_SECONDS)

        raise RuntimeError(
            f"searchFlights status={last_status!r}, no itineraries for "
            f"{origin}->{destination} after {self.RAPIDAPI_MAX_ATTEMPTS} attempts."
        )

    # --- other providers (skeletons) ---------------------------------------

    def _search_kiwi(self, origin, destination, depart_day):
        raise NotImplementedError("Kiwi (Tequila) integration not wired yet.")

    def _search_skyscanner(self, origin, destination, depart_day):
        raise NotImplementedError("Direct Skyscanner integration not wired yet.")

    def _search_serpapi(self, origin, destination, depart_day):
        raise NotImplementedError("SerpAPI Google Flights integration not wired yet.")


def get_fetcher(config) -> FlightFetcher:
    """Return the configured fetcher.

    Falls back to the placeholder fetcher whenever the selected live
    provider has no API key, so the bot always keeps running.
    """
    provider = (config.flight_api_provider or "placeholder").lower()

    if provider == "placeholder":
        return PlaceholderFlightFetcher()

    if provider == "rapidapi_skyscanner":
        if not config.rapidapi_key:
            log.warning("RapidAPI key missing - using placeholder fallback.")
            return PlaceholderFlightFetcher()
        return LiveFlightFetcher(
            provider,
            config.flight_api_key,
            config.flight_api_secret,
            rapidapi_key=config.rapidapi_key,
            rapidapi_host=config.rapidapi_host,
        )

    if provider == "amadeus":
        if not config.flight_api_key:
            log.warning("Amadeus key missing - using placeholder fallback.")
            return PlaceholderFlightFetcher()
        return LiveFlightFetcher(
            provider, config.flight_api_key, config.flight_api_secret
        )

    if not config.flight_api_key:
        return PlaceholderFlightFetcher()
    return LiveFlightFetcher(
        provider, config.flight_api_key, config.flight_api_secret
    )
