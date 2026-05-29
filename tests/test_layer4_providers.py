"""Layer 4 — provider tests (mock, AirDNA stub, Inside Airbnb stub).

Covers:
    - MockLodgingProvider emits one observation per stay-day
    - MockLodgingProvider forced_status round-trip
    - AirDnaProvider returns STUB when not configured AND when configured
    - InsideAirbnbProvider returns STUB when not configured AND when
      configured with a path (live wire still closed)
    - LodgingIntelService.refresh_observations integrates all three
      cleanly, persists mock data, skips stubs

Runnable directly:
    python tests/test_layer4_providers.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.sqlite_manager import SqliteManager
from intel.lodging import LodgingIntelService, LodgingStorage
from intel.lodging.providers import (
    AirDnaProvider,
    InsideAirbnbProvider,
    LodgingProvider,
    MockLodgingProvider,
    ProviderStatus,
)


T0 = datetime(2026, 5, 28, 12, 0, 0)


# ---------- MockLodgingProvider ----------

def test_mock_provider_returns_one_per_day():
    provider = MockLodgingProvider()
    result = provider.fetch(city="BOG", lookback_days=10, now=T0)
    assert result.status is ProviderStatus.OK
    assert len(result.observations) == 10
    assert all(o.city == "BOG" for o in result.observations)


def test_mock_provider_samples_per_day():
    provider = MockLodgingProvider(samples_per_day=3)
    result = provider.fetch(city="BOG", lookback_days=5, now=T0)
    assert len(result.observations) == 15


def test_mock_provider_forced_empty():
    provider = MockLodgingProvider(forced_status=ProviderStatus.EMPTY,
                                   forced_reason="no inventory")
    result = provider.fetch(city="BOG", now=T0)
    assert result.status is ProviderStatus.EMPTY
    assert result.observations == ()
    assert "no inventory" in result.reason


def test_mock_provider_forced_error():
    provider = MockLodgingProvider(forced_status=ProviderStatus.ERROR,
                                   forced_reason="503 upstream")
    result = provider.fetch(city="BOG", now=T0)
    assert result.status is ProviderStatus.ERROR


def test_mock_provider_is_valid_lodgingprovider():
    """Runtime protocol check — anyone implementing fetch + name passes."""
    assert isinstance(MockLodgingProvider(), LodgingProvider)


# ---------- AirDnaProvider STUB ----------

def test_airdna_unconfigured_is_stub():
    p = AirDnaProvider()
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB
    assert r.observations == ()
    assert "AirDNA" in r.reason or "AIRDNA" in r.reason.upper()


def test_airdna_with_key_but_no_enable_is_stub():
    p = AirDnaProvider(api_key="abc123")  # enable_live=False default
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB


def test_airdna_with_key_and_enable_still_stub_in_layer4():
    """Even with credentials AND explicit opt-in, Layer 4 keeps the
    wire path closed. This is the safety contract."""
    p = AirDnaProvider(api_key="abc123", enable_live=True)
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB
    assert "not implemented in Layer 4" in r.reason


# ---------- InsideAirbnbProvider STUB ----------

def test_inside_airbnb_unconfigured_is_stub():
    p = InsideAirbnbProvider()
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB


def test_inside_airbnb_with_path_no_enable_is_stub():
    p = InsideAirbnbProvider(local_path=Path("/tmp/insideairbnb"))
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB


def test_inside_airbnb_with_path_and_enable_still_stub():
    p = InsideAirbnbProvider(local_path=Path("/tmp/insideairbnb"),
                             enable_live=True)
    r = p.fetch(city="BOG", now=T0)
    assert r.status is ProviderStatus.STUB
    assert "not implemented" in r.reason


# ---------- Integration through LodgingIntelService ----------

def _service(*providers):
    mgr = SqliteManager(":memory:", dry_run=True)
    return LodgingIntelService(
        storage=LodgingStorage(mgr),
        providers=list(providers),
        lookback_days=14,
    )


def test_service_persists_mock_observations_and_skips_stubs():
    svc = _service(
        MockLodgingProvider(),
        AirDnaProvider(),         # STUB
        InsideAirbnbProvider(),   # STUB
    )
    results = svc.refresh_observations(city="BOG", now=T0)
    assert [r.status for r in results] == [
        ProviderStatus.OK, ProviderStatus.STUB, ProviderStatus.STUB,
    ]
    history = svc.storage.history_for("BOG")
    assert len(history) == 14   # one per day from mock


def test_service_disabled_returns_empty_list():
    svc = _service(MockLodgingProvider())
    svc.enabled = False
    assert svc.refresh_observations(city="BOG", now=T0) == []


def test_service_catches_provider_exception_and_marks_error():
    class _Broken:
        name = "broken"

        def fetch(self, **_):
            raise RuntimeError("boom")

    svc = _service(_Broken())
    results = svc.refresh_observations(city="BOG", now=T0)
    assert results[0].status is ProviderStatus.ERROR
    assert "boom" in results[0].reason


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
    print(f"\nLayer 4 providers: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
