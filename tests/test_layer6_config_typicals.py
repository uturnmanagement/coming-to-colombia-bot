"""Layer 6 — India config-driven per-category typical prices (O3).

Covers:
    - load_category_typicals_from_env: unset env -> None (defaults win)
    - valid JSON file -> mapped table (unknown keys ignored, bad values
      skipped)
    - missing / malformed / non-object file -> None (degrade quietly)
    - India() with no env keeps typical_prices=None (Layer 5 behavior)
    - India() with the env set loads the override table

Runnable directly:
    python tests/test_layer6_config_typicals.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.india import AccommodationCategory, India
from agents.india.scoring import (
    TYPICAL_PRICES_ENV_VAR,
    load_category_typicals_from_env,
)


def _write_json(obj) -> str:
    fh = tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    )
    json.dump(obj, fh)
    fh.close()
    return fh.name


# ---------- loader ----------

def test_unset_env_returns_none():
    assert load_category_typicals_from_env(env={}) is None


def test_valid_file_maps_table():
    path = _write_json({"hostel_dorm": 18, "budget_hotel": 55})
    table = load_category_typicals_from_env(env={TYPICAL_PRICES_ENV_VAR: path})
    assert table is not None
    assert table[AccommodationCategory.HOSTEL_DORM] == 18.0
    assert table[AccommodationCategory.BUDGET_HOTEL] == 55.0
    # untouched categories are simply absent (scoring falls back per-key)
    assert AccommodationCategory.GUEST_HOUSE not in table


def test_unknown_keys_and_bad_values_skipped():
    path = _write_json({
        "hostel_dorm": 20,
        "penthouse": 999,        # not a known category
        "budget_hotel": "free",  # not numeric
        "guest_house": -5,       # non-positive
    })
    table = load_category_typicals_from_env(env={TYPICAL_PRICES_ENV_VAR: path})
    assert table == {AccommodationCategory.HOSTEL_DORM: 20.0}


def test_missing_file_returns_none():
    table = load_category_typicals_from_env(
        env={TYPICAL_PRICES_ENV_VAR: "/no/such/file_xyz.json"}
    )
    assert table is None


def test_non_object_json_returns_none():
    path = _write_json([1, 2, 3])
    table = load_category_typicals_from_env(env={TYPICAL_PRICES_ENV_VAR: path})
    assert table is None


def test_empty_object_returns_none():
    path = _write_json({})
    table = load_category_typicals_from_env(env={TYPICAL_PRICES_ENV_VAR: path})
    assert table is None


# ---------- India wiring (reads os.environ via __post_init__) ----------

def test_india_without_env_uses_defaults():
    prev = os.environ.pop(TYPICAL_PRICES_ENV_VAR, None)
    try:
        india = India()
        assert india.typical_prices is None  # -> scoring module defaults
    finally:
        if prev is not None:
            os.environ[TYPICAL_PRICES_ENV_VAR] = prev


def test_india_with_env_loads_override():
    path = _write_json({"hostel_dorm": 22})
    prev = os.environ.get(TYPICAL_PRICES_ENV_VAR)
    os.environ[TYPICAL_PRICES_ENV_VAR] = path
    try:
        india = India()
        assert india.typical_prices == {AccommodationCategory.HOSTEL_DORM: 22.0}
    finally:
        if prev is None:
            os.environ.pop(TYPICAL_PRICES_ENV_VAR, None)
        else:
            os.environ[TYPICAL_PRICES_ENV_VAR] = prev


def test_india_explicit_override_beats_env():
    """An explicitly-passed table must not be clobbered by the env."""
    path = _write_json({"hostel_dorm": 22})
    prev = os.environ.get(TYPICAL_PRICES_ENV_VAR)
    os.environ[TYPICAL_PRICES_ENV_VAR] = path
    try:
        explicit = {AccommodationCategory.HOSTEL_DORM: 99.0}
        india = India(typical_prices=explicit)
        assert india.typical_prices == explicit
    finally:
        if prev is None:
            os.environ.pop(TYPICAL_PRICES_ENV_VAR, None)
        else:
            os.environ[TYPICAL_PRICES_ENV_VAR] = prev


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
    print(f"\nLayer 6 config typicals: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
