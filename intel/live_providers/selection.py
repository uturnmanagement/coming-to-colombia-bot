"""Environment-based live-provider selection.

Resolves which provider to use from env, defaulting to the deterministic
mock so the system is safe and offline out of the box. A "live" provider
name only activates real behavior when the master gate
``LIVE_PROVIDERS_ENABLE`` is true AND the relevant API key is set — and
even then Layer 7A's default transport keeps the wire closed (returns
ERROR 'not wired') until a real transport is supplied in a later layer.

Env knobs:
    LIVE_PROVIDERS_ENABLE          master gate (default false)
    LIVE_AIRFARE_PROVIDER          mock | generic   (default mock)
    LIVE_LODGING_PROVIDER          mock | generic   (default mock)
    LIVE_AIRFARE_API_KEY           secret (never logged)
    LIVE_LODGING_API_KEY           secret (never logged)
    LIVE_PROVIDER_TIMEOUT_SECONDS  per-request budget (default 8)
"""
from __future__ import annotations

import os
from typing import Optional

from agents.logging_setup import get_logger
from .airfare import LiveAirfareProvider, make_live_airfare_provider
from .lodging import LiveLodgingProvider, make_live_lodging_provider
from .mock import make_mock_airfare_provider, make_mock_lodging_provider

log = get_logger("live_providers")

_TRUE = {"1", "true", "yes", "on"}


def _get(env: dict, name: str, default: str = "") -> str:
    val = env.get(name)
    return val if val not in (None, "") else default


def _bool(env: dict, name: str, default: bool = False) -> bool:
    raw = _get(env, name, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _timeout(env: dict) -> float:
    try:
        return float(_get(env, "LIVE_PROVIDER_TIMEOUT_SECONDS", "8"))
    except ValueError:
        return 8.0


def build_airfare_provider(env: Optional[dict] = None) -> LiveAirfareProvider:
    env = os.environ if env is None else env
    name = _get(env, "LIVE_AIRFARE_PROVIDER", "mock").lower()
    if name == "mock":
        return make_mock_airfare_provider()
    if name != "generic":
        log.warning("unknown LIVE_AIRFARE_PROVIDER=%r; falling back to mock", name)
        return make_mock_airfare_provider()
    # A live adapter: gated by the master switch + key. Default transport
    # is closed (Layer 7A), so this is inert until wired later.
    return make_live_airfare_provider(
        enable_live=_bool(env, "LIVE_PROVIDERS_ENABLE", False),
        api_key=_get(env, "LIVE_AIRFARE_API_KEY"),
        timeout_seconds=_timeout(env),
    )


def build_lodging_provider(env: Optional[dict] = None) -> LiveLodgingProvider:
    env = os.environ if env is None else env
    name = _get(env, "LIVE_LODGING_PROVIDER", "mock").lower()
    if name == "mock":
        return make_mock_lodging_provider()
    if name != "generic":
        log.warning("unknown LIVE_LODGING_PROVIDER=%r; falling back to mock", name)
        return make_mock_lodging_provider()
    return make_live_lodging_provider(
        enable_live=_bool(env, "LIVE_PROVIDERS_ENABLE", False),
        api_key=_get(env, "LIVE_LODGING_API_KEY"),
        timeout_seconds=_timeout(env),
    )
