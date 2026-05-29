"""Layer 4 — baseline + history SQLite storage tests.

Covers:
    - lodging_history insert + readback (round-trip)
    - lodging_baseline save + latest lookup
    - latest_baseline returns the most recent row when multiple stored
    - latest_baseline lookup respects city / neighborhood / beds filters
    - history_for filter by neighborhood + beds
    - compute_baseline + storage round-trip yields consistent fields

Runnable directly:
    python tests/test_layer4_storage.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.sqlite_manager import SqliteManager
from intel.lodging import LodgingBaseline, LodgingStorage, compute_baseline
from intel.lodging.providers import LodgingObservation


T0 = datetime(2026, 5, 28, 12, 0, 0)


def _storage() -> LodgingStorage:
    mgr = SqliteManager(":memory:", dry_run=True)
    return LodgingStorage(mgr)


def _obs(city="BOG", days_ago=10, price=60.0, neighborhood=None, beds=None,
         source="mock"):
    when = T0 - timedelta(days=days_ago)
    return LodgingObservation(
        city=city, neighborhood=neighborhood, beds=beds,
        observed_at=when, stay_date=when.date(),
        price_usd=price, source=source,
    )


# ---------- lodging_history round-trip ----------

def test_history_round_trip_basic():
    st = _storage()
    st.record_observation(_obs(price=60.0))
    st.record_observation(_obs(price=62.0, days_ago=8))
    rows = st.history_for("BOG")
    assert len(rows) == 2
    prices = sorted(r["price_usd"] for r in rows)
    assert prices == [60.0, 62.0]
    assert rows[0]["source"] == "mock"


def test_history_filters_by_neighborhood():
    st = _storage()
    st.record_observation(_obs(neighborhood="El Poblado", price=70.0))
    st.record_observation(_obs(neighborhood="Laureles", price=55.0))
    rows = st.history_for("BOG", neighborhood="El Poblado")
    assert len(rows) == 1
    assert rows[0]["price_usd"] == 70.0


def test_history_filters_by_beds():
    st = _storage()
    st.record_observation(_obs(beds=1, price=50.0))
    st.record_observation(_obs(beds=2, price=80.0))
    rows = st.history_for("BOG", beds=2)
    assert len(rows) == 1
    assert rows[0]["beds"] == 2


# ---------- baseline persistence ----------

def test_save_and_latest_baseline_basic():
    st = _storage()
    b = LodgingBaseline(
        city="BOG", neighborhood=None, beds=None,
        baseline_price_usd=62.0, sample_size=30, lookback_days=90,
        computed_at=T0, source_set=("mock",),
    )
    st.save_baseline(b)
    row = st.latest_baseline("BOG")
    assert row is not None
    assert row["baseline_price_usd"] == 62.0
    assert row["sample_size"] == 30
    assert row["lookback_days"] == 90
    assert row["source_set"] == "mock"


def test_latest_baseline_returns_newest():
    st = _storage()
    older = LodgingBaseline(
        city="BOG", neighborhood=None, beds=None,
        baseline_price_usd=58.0, sample_size=20, lookback_days=90,
        computed_at=T0 - timedelta(days=2),
    )
    newer = LodgingBaseline(
        city="BOG", neighborhood=None, beds=None,
        baseline_price_usd=64.0, sample_size=35, lookback_days=90,
        computed_at=T0,
    )
    st.save_baseline(older)
    st.save_baseline(newer)
    row = st.latest_baseline("BOG")
    assert row["baseline_price_usd"] == 64.0


def test_latest_baseline_filters_by_neighborhood():
    st = _storage()
    st.save_baseline(LodgingBaseline(
        city="BOG", neighborhood=None, beds=None,
        baseline_price_usd=60.0, sample_size=10, lookback_days=90,
        computed_at=T0,
    ))
    st.save_baseline(LodgingBaseline(
        city="BOG", neighborhood="Chapinero", beds=None,
        baseline_price_usd=85.0, sample_size=10, lookback_days=90,
        computed_at=T0,
    ))
    base_all = st.latest_baseline("BOG")
    base_chap = st.latest_baseline("BOG", neighborhood="Chapinero")
    assert base_all["baseline_price_usd"] == 60.0
    assert base_chap["baseline_price_usd"] == 85.0


def test_latest_baseline_filters_by_beds():
    st = _storage()
    st.save_baseline(LodgingBaseline(
        city="BOG", neighborhood=None, beds=1,
        baseline_price_usd=45.0, sample_size=10, lookback_days=90,
        computed_at=T0,
    ))
    st.save_baseline(LodgingBaseline(
        city="BOG", neighborhood=None, beds=2,
        baseline_price_usd=75.0, sample_size=10, lookback_days=90,
        computed_at=T0,
    ))
    row = st.latest_baseline("BOG", beds=2)
    assert row["baseline_price_usd"] == 75.0


# ---------- baseline aggregation + storage round-trip ----------

def test_compute_baseline_returns_none_for_empty():
    out = compute_baseline([], lookback_days=90, now=T0, city="BOG")
    assert out is None


def test_compute_baseline_uses_median():
    obs = [_obs(price=p, days_ago=i) for i, p in
           enumerate([50, 60, 80, 100, 200], start=1)]
    b = compute_baseline(obs, lookback_days=90, now=T0, city="BOG")
    assert b is not None
    assert b.baseline_price_usd == 80.0   # median of 5 values
    assert b.sample_size == 5


def test_compute_baseline_drops_observations_outside_window():
    obs = [
        _obs(price=50, days_ago=200),   # outside 90-day window
        _obs(price=60, days_ago=30),
        _obs(price=62, days_ago=15),
    ]
    b = compute_baseline(obs, lookback_days=90, now=T0, city="BOG")
    assert b is not None
    assert b.sample_size == 2
    assert b.baseline_price_usd == 61.0  # median of 60 and 62


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
    print(f"\nLayer 4 storage: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
