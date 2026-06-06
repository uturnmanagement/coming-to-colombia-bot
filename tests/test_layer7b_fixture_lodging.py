"""Phase 6B — dark, fixture-backed live lodging provider.

Exercises the recorded-snapshot transport end-to-end through the real
``LiveLodgingProvider`` pipeline. Everything here is offline: the data
comes from committed JSON fixtures, never an API. Covers:

  - recorded fixtures exist for every city in the canonical registry;
  - OK + normalization, and determinism, on recorded data;
  - EMPTY for unknown / missing city (mirrors a real no-listings reply);
  - the LiveProvider gate (DISABLED / NO_KEY) still applies to the
    fixture transport, so recorded data never leaks without opt-in;
  - a custom fixtures_dir works and an empty dir degrades to EMPTY;
  - selection routing: default stays mock (dark); fixture only arms on
    explicit LIVE_LODGING_PROVIDER=fixture;
  - a static guarantee that the transport module imports nothing that
    could reach the network;
  - fetch never raises across every mode.

Runnable directly:
    python tests/test_layer7b_fixture_lodging.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.live_providers import (
    FIXTURE_API_KEY,
    FIXTURES_DIR,
    FixtureLodgingTransport,
    LiveProviderStatus,
    LodgingQuote,
    build_lodging_provider,
    make_fixture_lodging_provider,
    make_live_lodging_provider,
)
from intel.live_providers import fixture_transport as ft_module
from lodging.lodging_models import CITY_REGISTRY


# ---------- fixtures exist + are well-formed ----------

def test_fixture_exists_for_every_registry_city():
    have = {p.stem for p in FIXTURES_DIR.glob("*.json")}
    want = {c.code for c in CITY_REGISTRY}
    assert want.issubset(have), f"missing fixtures for: {want - have}"


def test_every_fixture_marks_itself_recorded_not_live():
    for c in CITY_REGISTRY:
        payload = json.loads((FIXTURES_DIR / f"{c.code}.json").read_text("utf-8"))
        meta = payload["_meta"]
        assert meta["city_code"] == c.code
        assert meta["recorded_at"]              # frozen snapshot date present
        assert "NOT live" in meta["note"]       # honesty marker
        assert payload["listings"]              # at least one listing


def test_every_fixture_flows_through_provider_as_ok():
    prov = make_fixture_lodging_provider()
    for c in CITY_REGISTRY:
        res = prov.fetch(city=c.code)
        assert res.status is LiveProviderStatus.OK, c.code
        assert res.is_usable and res.data
        assert all(isinstance(q, LodgingQuote) for q in res.data)


# ---------- OK + normalization + determinism ----------

def test_known_city_ok_and_normalized():
    res = make_fixture_lodging_provider().fetch(city="BOG")
    assert res.status is LiveProviderStatus.OK
    assert res.source == "fixture_lodging"
    q = res.data[0]
    assert q.city == "BOG"                 # uppercased by the parser
    assert q.price_usd > 0 and q.beds == 1
    assert q.listing_ref == "rec-BOG-1"


def test_lowercase_city_is_normalized():
    res = make_fixture_lodging_provider().fetch(city="mde")
    assert res.status is LiveProviderStatus.OK
    assert all(q.city == "MDE" for q in res.data)


def test_recorded_data_is_deterministic():
    prov = make_fixture_lodging_provider()
    a = prov.fetch(city="CTG").data
    b = prov.fetch(city="CTG").data
    assert a == b                          # frozen snapshot, no randomness


# ---------- EMPTY paths ----------

def test_unknown_city_is_empty():
    res = make_fixture_lodging_provider().fetch(city="ZZZ")
    assert res.status is LiveProviderStatus.EMPTY
    assert not res.data


def test_missing_city_param_is_empty():
    res = make_fixture_lodging_provider().fetch()
    assert res.status is LiveProviderStatus.EMPTY


# ---------- gating still applies to the fixture transport ----------

def _gated(*, enable_live, api_key):
    # Same recorded transport, but built through the gated factory so we
    # can flip the LiveProvider gates and prove recorded data is withheld.
    return make_live_lodging_provider(
        enable_live=enable_live, api_key=api_key,
        transport=FixtureLodgingTransport(),
    )


def test_disabled_gate_withholds_recorded_data():
    t = FixtureLodgingTransport()
    prov = make_live_lodging_provider(enable_live=False, api_key="k", transport=t)
    res = prov.fetch(city="BOG")
    assert res.status is LiveProviderStatus.DISABLED
    assert t.last_call is None              # transport never touched


def test_no_key_gate_withholds_recorded_data():
    t = FixtureLodgingTransport()
    prov = make_live_lodging_provider(enable_live=True, api_key="", transport=t)
    res = prov.fetch(city="BOG")
    assert res.status is LiveProviderStatus.NO_KEY
    assert t.last_call is None


def test_fixture_factory_is_self_gated_open():
    # The shipped factory supplies a sentinel key so the pipeline runs,
    # but the key is not a real secret.
    assert FIXTURE_API_KEY == "fixture"
    assert make_fixture_lodging_provider().fetch(city="BOG").is_usable


# ---------- custom + empty fixtures_dir ----------

def test_custom_fixtures_dir(tmp_path_factory=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ddir = Path(d)
        (ddir / "XXX.json").write_text(json.dumps({
            "_meta": {"city_code": "XXX"},
            "listings": [{"city": "XXX", "price_usd": 9.5, "beds": 1}],
        }), "utf-8")
        prov = make_fixture_lodging_provider(fixtures_dir=ddir)
        res = prov.fetch(city="XXX")
        assert res.status is LiveProviderStatus.OK
        assert res.data[0].price_usd == 9.5


def test_empty_fixtures_dir_is_empty_not_error():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        t = FixtureLodgingTransport(fixtures_dir=Path(d))
        assert t.available_cities() == ()
        prov = make_live_lodging_provider(
            enable_live=True, api_key="fixture", transport=t)
        assert prov.fetch(city="BOG").status is LiveProviderStatus.EMPTY


def test_available_cities_lists_registry():
    cities = set(FixtureLodgingTransport().available_cities())
    assert {c.code for c in CITY_REGISTRY}.issubset(cities)


# ---------- selection routing: dark by default ----------

def test_selection_defaults_to_mock():
    assert build_lodging_provider(env={}).name == "mock_lodging"


def test_selection_fixture_opt_in():
    prov = build_lodging_provider(env={"LIVE_LODGING_PROVIDER": "fixture"})
    assert prov.name == "fixture_lodging"
    assert prov.fetch(city="BOG").is_usable


def test_selection_unknown_falls_back_to_mock():
    assert build_lodging_provider(
        env={"LIVE_LODGING_PROVIDER": "bogus"}).name == "mock_lodging"


# ---------- no-network guarantee ----------

def test_transport_module_imports_nothing_networked():
    src = Path(ft_module.__file__).read_text("utf-8")
    for banned in ("import requests", "import socket", "import urllib",
                   "import http", "from requests", "from urllib", "from http"):
        assert banned not in src, f"fixture transport must not use {banned!r}"


def test_last_call_records_request_without_secret_leak():
    t = FixtureLodgingTransport()
    make_live_lodging_provider(
        enable_live=True, api_key="fixture", transport=t).fetch(city="bog")
    assert t.last_call["city"] == "BOG"
    assert t.last_call["api_key"] == "fixture"


# ---------- never raises ----------

def test_fetch_never_raises_for_any_mode():
    cases = [
        make_fixture_lodging_provider(),
        _gated(enable_live=False, api_key="k"),
        _gated(enable_live=True, api_key=""),
        _gated(enable_live=True, api_key="fixture"),
    ]
    queries = [{"city": "BOG"}, {"city": "zzz"}, {}]
    for prov in cases:
        for q in queries:
            res = prov.fetch(**q)           # must not raise
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
    print(f"\nLayer 7B fixture lodging: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
