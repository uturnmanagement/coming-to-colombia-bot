"""Layer 7A — live provider base: gating + the five failure modes.

Exercises the whole LiveProvider pipeline with an InjectableTransport so
there is NO external API call. Covers, for both airfare and lodging:
    OK / EMPTY (empty list + None payload) / MALFORMED / TIMEOUT /
    ERROR / NO_KEY / DISABLED, and that fetch never raises.

Runnable directly:
    python tests/test_layer7a_live_providers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.live_providers import (
    AirfareQuote,
    InjectableTransport,
    LiveProviderStatus,
    LodgingQuote,
    ProviderTimeout,
    ProviderTransportError,
    make_live_airfare_provider,
    make_live_lodging_provider,
)

_GOOD_AIR = {"quotes": [
    {"origin": "bwi", "destination": "bog", "price_usd": "285",
     "depart_date": "2026-06-01", "carrier": "AV"},
]}
_GOOD_LODGE = {"listings": [
    {"city": "bog", "price_usd": 22.0, "beds": 1,
     "neighborhood": "La Candelaria"},
]}


def _air(*, response=None, error=None, enable_live=True, api_key="k"):
    return make_live_airfare_provider(
        enable_live=enable_live, api_key=api_key,
        transport=InjectableTransport(response=response, error=error),
    )


def _lodge(*, response=None, error=None, enable_live=True, api_key="k"):
    return make_live_lodging_provider(
        enable_live=enable_live, api_key=api_key,
        transport=InjectableTransport(response=response, error=error),
    )


# ---------- OK ----------

def test_airfare_ok_normalizes_records():
    res = _air(response=_GOOD_AIR).fetch(origin="BWI", destination="BOG")
    assert res.status is LiveProviderStatus.OK
    assert res.is_usable
    assert isinstance(res.data[0], AirfareQuote)
    assert res.data[0].origin == "BWI" and res.data[0].price_usd == 285.0


def test_lodging_ok_normalizes_records():
    res = _lodge(response=_GOOD_LODGE).fetch(city="BOG")
    assert res.status is LiveProviderStatus.OK
    assert isinstance(res.data[0], LodgingQuote)
    assert res.data[0].city == "BOG" and res.data[0].beds == 1


# ---------- EMPTY ----------

def test_empty_list_is_empty():
    assert _air(response={"quotes": []}).fetch().status is LiveProviderStatus.EMPTY
    assert _lodge(response={"listings": []}).fetch().status is LiveProviderStatus.EMPTY


def test_none_payload_is_empty():
    assert _air(response=None).fetch().status is LiveProviderStatus.EMPTY


# ---------- MALFORMED ----------

def test_missing_key_field_is_malformed():
    assert _air(response={"nope": 1}).fetch().status is LiveProviderStatus.MALFORMED


def test_wrong_type_is_malformed():
    assert _air(response={"quotes": "notalist"}).fetch().status is LiveProviderStatus.MALFORMED
    bad = {"listings": [{"city": "BOG", "price_usd": "free"}]}  # float() raises
    assert _lodge(response=bad).fetch().status is LiveProviderStatus.MALFORMED


# ---------- TIMEOUT / ERROR ----------

def test_timeout_maps_to_timeout():
    res = _air(error=ProviderTimeout("slow")).fetch()
    assert res.status is LiveProviderStatus.TIMEOUT


def test_transport_error_maps_to_error():
    res = _air(error=ProviderTransportError("boom")).fetch()
    assert res.status is LiveProviderStatus.ERROR


def test_unexpected_exception_maps_to_error():
    res = _air(error=RuntimeError("kaboom")).fetch()
    assert res.status is LiveProviderStatus.ERROR


# ---------- NO_KEY / DISABLED (wire never touched) ----------

def test_no_key_when_enabled_without_key():
    t = InjectableTransport(response=_GOOD_AIR)
    prov = make_live_airfare_provider(enable_live=True, api_key="", transport=t)
    res = prov.fetch()
    assert res.status is LiveProviderStatus.NO_KEY
    assert t.last_call is None  # transport must NOT have been called


def test_disabled_by_default():
    t = InjectableTransport(response=_GOOD_AIR)
    prov = make_live_airfare_provider(enable_live=False, api_key="k", transport=t)
    res = prov.fetch()
    assert res.status is LiveProviderStatus.DISABLED
    assert t.last_call is None


# ---------- never raises ----------

def test_fetch_never_raises_for_any_mode():
    cases = [
        _air(response=_GOOD_AIR),
        _air(response=None),
        _air(response={"quotes": []}),
        _air(response={"bad": 1}),
        _air(error=ProviderTimeout()),
        _air(error=RuntimeError()),
        _air(enable_live=False),
        _air(api_key=""),
    ]
    for prov in cases:
        res = prov.fetch()  # must not raise
        assert isinstance(res.status, LiveProviderStatus)


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
    print(f"\nLayer 7A live providers: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
