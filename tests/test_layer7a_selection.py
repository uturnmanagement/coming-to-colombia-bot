"""Layer 7A — environment-based provider selection.

All selection runs are driven by an injected env dict (no os.environ
mutation, no external API). Covers:
    - default (no env) -> deterministic mock, returns OK
    - explicit mock mode
    - generic + master disabled -> DISABLED
    - generic + enabled, missing key -> NO_KEY
    - generic + enabled + key -> ERROR ('not wired' in Layer 7A)
    - unknown provider name -> safe mock fallback

Runnable directly:
    python tests/test_layer7a_selection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.live_providers import (
    LiveProviderStatus,
    build_airfare_provider,
    build_lodging_provider,
)


# ---------- defaults / mock ----------

def test_default_is_mock_and_ok():
    res = build_airfare_provider(env={}).fetch(origin="BWI", destination="BOG")
    assert res.status is LiveProviderStatus.OK
    assert res.is_usable
    lres = build_lodging_provider(env={}).fetch(city="BOG")
    assert lres.status is LiveProviderStatus.OK


def test_explicit_mock_mode():
    env = {"LIVE_AIRFARE_PROVIDER": "mock", "LIVE_LODGING_PROVIDER": "mock"}
    assert build_airfare_provider(env=env).fetch().status is LiveProviderStatus.OK
    assert build_lodging_provider(env=env).fetch().status is LiveProviderStatus.OK


# ---------- generic (live) name, gated ----------

def test_generic_disabled_returns_disabled():
    env = {"LIVE_AIRFARE_PROVIDER": "generic", "LIVE_PROVIDERS_ENABLE": "false",
           "LIVE_AIRFARE_API_KEY": "secret"}
    assert build_airfare_provider(env=env).fetch().status is LiveProviderStatus.DISABLED


def test_generic_enabled_missing_key_returns_no_key():
    env = {"LIVE_AIRFARE_PROVIDER": "generic", "LIVE_PROVIDERS_ENABLE": "true"}
    assert build_airfare_provider(env=env).fetch().status is LiveProviderStatus.NO_KEY


def test_generic_enabled_with_key_is_not_wired_error():
    """Even fully configured, Layer 7A keeps the wire closed (no network)."""
    env = {"LIVE_LODGING_PROVIDER": "generic", "LIVE_PROVIDERS_ENABLE": "true",
           "LIVE_LODGING_API_KEY": "secret"}
    res = build_lodging_provider(env=env).fetch(city="BOG")
    assert res.status is LiveProviderStatus.ERROR
    assert "not implemented" in res.reason.lower() or "not wired" in res.reason.lower()


# ---------- unknown name -> safe fallback ----------

def test_unknown_provider_falls_back_to_mock():
    env = {"LIVE_AIRFARE_PROVIDER": "wat"}
    assert build_airfare_provider(env=env).fetch().status is LiveProviderStatus.OK


# ---------- runner ----------

def _all_tests():
    return [(n, o) for n, o in globals().items()
            if n.startswith("test_") and callable(o)]


def main():
    passed = failed = 0
    for name, fn in _all_tests():
        try:
            fn()
            passed += 1
            print(f"  ok   {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {name}: {type(exc).__name__}: {exc}")
    print(f"\nLayer 7A selection: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
