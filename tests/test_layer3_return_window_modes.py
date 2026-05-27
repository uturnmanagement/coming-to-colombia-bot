"""Layer 3 enhancement — configurable return-window modes.

Covers:
    - resolve_return_windows() defaults to the canonical 8-window list
    - fixed-mode env override via RETURN_WINDOWS_DAYS
    - range mode generates every integer from 4 through 60 inclusive
    - range mode with non-1 steps
    - input validation: bad mode, bad step, bad min/max, empty list
    - Delta picks up resolved windows at construction
    - Delta accepts explicit windows= override at both construction and
      analyze() call sites
    - Existing Layer 3 invariants (canonical default behavior) still hold

Runnable directly:
    python tests/test_layer3_return_window_modes.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.delta import Delta
from agents.oakstreet import AlertEvent
from intel.return_pairing import (
    RETURN_WINDOWS_DAYS,
    ReturnWindowMode,
    parse_fixed_list,
    range_windows,
    resolve_return_windows,
)


T0 = datetime(2026, 5, 27, 10, 0, 0)


def _event():
    return AlertEvent(
        deal_id="DEAL-WM",
        color="red",
        price_usd=285.0,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


# ---------- resolve_return_windows (env-driven) ----------

def test_resolve_default_is_fixed_canonical():
    """No env vars set → canonical 8-window list. Non-breaking default."""
    assert resolve_return_windows(env={}) == RETURN_WINDOWS_DAYS


def test_resolve_fixed_mode_explicit():
    out = resolve_return_windows(env={"RETURN_WINDOW_MODE": "fixed"})
    assert out == RETURN_WINDOWS_DAYS


def test_resolve_fixed_mode_with_override_list():
    out = resolve_return_windows(env={
        "RETURN_WINDOW_MODE": "fixed",
        "RETURN_WINDOWS_DAYS": "3,5,8,13",
    })
    assert out == (3, 5, 8, 13)


def test_resolve_fixed_mode_override_tolerates_whitespace():
    out = resolve_return_windows(env={
        "RETURN_WINDOWS_DAYS": " 4 , 7,10 ,14",
    })
    assert out == (4, 7, 10, 14)


def test_resolve_unknown_mode_raises():
    try:
        resolve_return_windows(env={"RETURN_WINDOW_MODE": "monthly"})
    except ValueError as exc:
        assert "RETURN_WINDOW_MODE" in str(exc)
        return
    raise AssertionError("unknown mode must raise")


def test_resolve_case_insensitive_mode():
    out = resolve_return_windows(env={
        "RETURN_WINDOW_MODE": "RANGE",
        "RETURN_MIN_DAYS": "4",
        "RETURN_MAX_DAYS": "10",
    })
    assert out == (4, 5, 6, 7, 8, 9, 10)


# ---------- RANGE MODE — explicit acceptance test ----------

def test_range_mode_generates_every_day_4_through_60():
    """The explicit Layer 3 enhancement ask: range mode produces every
    integer from 4 through 60 inclusive (57 windows)."""
    out = resolve_return_windows(env={
        "RETURN_WINDOW_MODE": "range",
        "RETURN_MIN_DAYS": "4",
        "RETURN_MAX_DAYS": "60",
        "RETURN_WINDOW_STEP_DAYS": "1",
    })
    assert out == tuple(range(4, 61))
    assert len(out) == 57
    assert out[0] == 4
    assert out[-1] == 60
    # Spot-check three interior values to guard against off-by-one drift.
    assert 7 in out and 30 in out and 50 in out


def test_range_mode_uses_documented_defaults_when_keys_missing():
    """When only RETURN_WINDOW_MODE=range is set, the (4, 60, 1) defaults
    from the spec apply — same shape as the explicit case above."""
    out = resolve_return_windows(env={"RETURN_WINDOW_MODE": "range"})
    assert out == tuple(range(4, 61))


def test_range_mode_with_step_2():
    out = resolve_return_windows(env={
        "RETURN_WINDOW_MODE": "range",
        "RETURN_MIN_DAYS": "4",
        "RETURN_MAX_DAYS": "20",
        "RETURN_WINDOW_STEP_DAYS": "2",
    })
    assert out == (4, 6, 8, 10, 12, 14, 16, 18, 20)


def test_range_mode_with_step_skipping_max():
    """Step that doesn't land on RETURN_MAX_DAYS still stops at <= max."""
    out = resolve_return_windows(env={
        "RETURN_WINDOW_MODE": "range",
        "RETURN_MIN_DAYS": "4",
        "RETURN_MAX_DAYS": "10",
        "RETURN_WINDOW_STEP_DAYS": "3",
    })
    assert out == (4, 7, 10)


# ---------- range_windows direct ----------

def test_range_windows_inclusive_endpoints():
    assert range_windows(4, 60, 1) == tuple(range(4, 61))
    assert range_windows(4, 4, 1) == (4,)


def test_range_windows_validates_min():
    try:
        range_windows(0, 10, 1)
    except ValueError:
        return
    raise AssertionError("RETURN_MIN_DAYS=0 must raise")


def test_range_windows_validates_min_le_max():
    try:
        range_windows(20, 10, 1)
    except ValueError:
        return
    raise AssertionError("min > max must raise")


def test_range_windows_validates_step():
    try:
        range_windows(4, 10, 0)
    except ValueError:
        return
    raise AssertionError("step=0 must raise")


# ---------- parse_fixed_list ----------

def test_parse_fixed_list_basic():
    assert parse_fixed_list("4,7,10") == (4, 7, 10)


def test_parse_fixed_list_skips_empty_entries():
    assert parse_fixed_list("4,,7, ,10") == (4, 7, 10)


def test_parse_fixed_list_rejects_non_integer():
    try:
        parse_fixed_list("4,seven,10")
    except ValueError:
        return
    raise AssertionError("non-integer entry must raise")


def test_parse_fixed_list_rejects_nonpositive():
    try:
        parse_fixed_list("4,0,7")
    except ValueError:
        return
    raise AssertionError("zero / negative entry must raise")


def test_parse_fixed_list_rejects_empty_input():
    try:
        parse_fixed_list("")
    except ValueError:
        return
    raise AssertionError("empty input must raise")


# ---------- Delta consumes resolved windows ----------

def test_delta_default_construction_uses_canonical_list():
    """With no env vars set, Delta() resolves to the canonical 8 windows."""
    import os

    overridden_keys = (
        "RETURN_WINDOW_MODE",
        "RETURN_WINDOWS_DAYS",
        "RETURN_MIN_DAYS",
        "RETURN_MAX_DAYS",
        "RETURN_WINDOW_STEP_DAYS",
    )
    snapshot = {k: os.environ.pop(k, None) for k in overridden_keys}
    try:
        d = Delta()
        assert d.windows == RETURN_WINDOWS_DAYS
        rpt = d.analyze(_event())
        assert len(rpt.payload["options"]) == len(RETURN_WINDOWS_DAYS)
    finally:
        for k, v in snapshot.items():
            if v is not None:
                os.environ[k] = v


def test_delta_explicit_windows_override_construction():
    d = Delta(windows=(5, 10, 15))
    assert d.windows == (5, 10, 15)
    rpt = d.analyze(_event())
    assert [o["window_days"] for o in rpt.payload["options"]] == [5, 10, 15]


def test_delta_analyze_param_overrides_constructor():
    d = Delta(windows=(5, 10))
    rpt = d.analyze(_event(), windows=(7, 14, 21))
    assert [o["window_days"] for o in rpt.payload["options"]] == [7, 14, 21]


def test_delta_with_range_mode_via_env(monkeypatch=None):
    """Construct Delta after an env mutation; the resolver picks up the
    range mode at __post_init__ time."""
    import os

    snapshot = {
        k: os.environ.get(k)
        for k in ("RETURN_WINDOW_MODE", "RETURN_MIN_DAYS",
                  "RETURN_MAX_DAYS", "RETURN_WINDOW_STEP_DAYS")
    }
    os.environ["RETURN_WINDOW_MODE"] = "range"
    os.environ["RETURN_MIN_DAYS"] = "4"
    os.environ["RETURN_MAX_DAYS"] = "60"
    os.environ["RETURN_WINDOW_STEP_DAYS"] = "1"
    try:
        d = Delta()
        assert len(d.windows) == 57
        assert d.windows[0] == 4 and d.windows[-1] == 60
        rpt = d.analyze(_event())
        # Every window must end up in the payload.
        assert len(rpt.payload["options"]) == 57
    finally:
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------- runner ----------

def _all_tests():
    return [(name, obj) for name, obj in globals().items()
            if name.startswith("test_") and callable(obj)]


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
    print(f"\nLayer 3 window modes: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
