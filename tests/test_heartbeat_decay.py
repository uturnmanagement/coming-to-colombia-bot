"""Heartbeat decay engine — unit tests.

Covers stage classification, every material trigger, max-silence force,
zombie mute, and rate-limit suppression.

Runnable directly:
    python tests/test_heartbeat_decay.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.heartbeat import (  # noqa: E402
    AlertSnapshot,
    HeartbeatStage,
    classify_stage,
    decide_heartbeat,
    has_material_change,
    interval_for_stage,
)


T0 = datetime(2026, 5, 26, 10, 0, 0)


def snap(price=300.0, color="red", route="BWI->BOG direct", depart_offset_h=72.0,
         deal_id="d1"):
    return AlertSnapshot(
        deal_id=deal_id,
        color=color,
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=depart_offset_h),
    )


# ---------- stage classification ----------

def test_classify_stage_boundaries():
    assert classify_stage(0) is HeartbeatStage.ACTIVE
    assert classify_stage(3.9) is HeartbeatStage.ACTIVE
    assert classify_stage(4.0) is HeartbeatStage.COOLING
    assert classify_stage(23.9) is HeartbeatStage.COOLING
    assert classify_stage(24.0) is HeartbeatStage.STALE
    assert classify_stage(47.9) is HeartbeatStage.STALE
    assert classify_stage(48.0) is HeartbeatStage.ZOMBIE
    assert classify_stage(96.0) is HeartbeatStage.ZOMBIE


def test_intervals():
    assert interval_for_stage(HeartbeatStage.ACTIVE) == timedelta(minutes=15)
    assert interval_for_stage(HeartbeatStage.COOLING) == timedelta(hours=1)
    assert interval_for_stage(HeartbeatStage.STALE) == timedelta(hours=12)


# ---------- material triggers ----------

def test_trigger_price_threshold():
    prev = snap(price=300)
    curr = snap(price=304.99)
    changed, _ = has_material_change(prev, curr)
    assert changed is False, "sub-$5 movement must not trigger"
    curr = snap(price=305)
    changed, reason = has_material_change(prev, curr)
    assert changed is True and "price" in reason


def test_trigger_route():
    prev = snap(route="BWI->BOG direct")
    curr = snap(route="BWI->MIA->BOG")
    changed, reason = has_material_change(prev, curr)
    assert changed is True and "route" in reason


def test_trigger_color():
    prev = snap(color="yellow")
    curr = snap(color="red")
    changed, reason = has_material_change(prev, curr)
    assert changed is True and "color" in reason


def test_trigger_departure_shift():
    prev = snap(depart_offset_h=72.0)
    curr = snap(depart_offset_h=72.5)
    changed, reason = has_material_change(prev, curr)
    assert changed is True and "departure" in reason
    # Sub-30-min shift must not trigger.
    curr = snap(depart_offset_h=72.0 + 29/60)
    changed, _ = has_material_change(prev, curr)
    assert changed is False


# ---------- end-to-end decision ----------

def _decide(age_h, silence_h, prev=None, curr=None):
    now = T0 + timedelta(hours=age_h)
    first = T0
    last_hb = now - timedelta(hours=silence_h) if silence_h is not None else None
    return decide_heartbeat(
        previous=prev,
        current=curr or snap(),
        first_alert_at=first,
        last_heartbeat_at=last_hb,
        now=now,
    )


def test_zombie_mutes_everything():
    # Even with a clear price trigger, ZOMBIE must not emit.
    prev = snap(price=300)
    curr = snap(price=400)
    decision = _decide(age_h=72, silence_h=1, prev=prev, curr=curr)
    assert decision.should_emit is False
    assert decision.stage is HeartbeatStage.ZOMBIE


def test_active_emits_on_trigger_after_interval():
    prev = snap(price=300)
    curr = snap(price=320)
    decision = _decide(age_h=2, silence_h=1, prev=prev, curr=curr)
    assert decision.should_emit is True
    assert decision.stage is HeartbeatStage.ACTIVE


def test_active_rate_limits_within_interval():
    prev = snap(price=300)
    curr = snap(price=320)
    # 10 minutes since last heartbeat — under the 15-min ACTIVE interval.
    decision = _decide(age_h=1, silence_h=10/60, prev=prev, curr=curr)
    assert decision.should_emit is False
    assert "rate-limited" in decision.reason


def test_cooling_rate_limits_within_interval():
    prev = snap(price=300)
    curr = snap(price=320)
    # 30 min silence in COOLING stage (interval 1h) -> suppressed.
    decision = _decide(age_h=10, silence_h=0.5, prev=prev, curr=curr)
    assert decision.should_emit is False
    assert decision.stage is HeartbeatStage.COOLING


def test_max_silence_force_emit_no_change():
    # No material change but silence > 12h -> force keepalive.
    prev = snap(price=300)
    curr = snap(price=300)
    decision = _decide(age_h=20, silence_h=13, prev=prev, curr=curr)
    assert decision.should_emit is True
    assert "max silence" in decision.reason


def test_no_change_inside_max_silence_suppressed():
    prev = snap(price=300)
    curr = snap(price=300)
    decision = _decide(age_h=10, silence_h=2, prev=prev, curr=curr)
    assert decision.should_emit is False
    assert decision.reason == "no material change"


def test_stale_stage_uses_12h_interval():
    # 30h-old deal -> STALE. 6h silence < 12h interval -> rate-limit
    # even with a price change.
    prev = snap(price=300)
    curr = snap(price=320)
    decision = _decide(age_h=30, silence_h=6, prev=prev, curr=curr)
    assert decision.stage is HeartbeatStage.STALE
    assert decision.should_emit is False


def test_first_observation_treated_as_changed():
    decision = _decide(age_h=1, silence_h=None, prev=None, curr=snap())
    # With no last_heartbeat_at, silence is infinite -> max-silence path.
    assert decision.should_emit is True


# ---------- runner ----------

def _all_tests():
    return [(name, obj) for name, obj in globals().items()
            if name.startswith("test_") and callable(obj)]


def main():
    passed = failed = 0
    failures = []
    for name, fn in _all_tests():
        try:
            fn()
            passed += 1
            print(f"  ok   {name}")
        except AssertionError as exc:
            failed += 1
            failures.append((name, str(exc)))
            print(f"  FAIL {name}: {exc}")
    print(f"\nHeartbeat decay: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
