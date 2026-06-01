"""Color-driven heartbeat policy — unit tests (Phase 2.8).

Covers the policy spec directly against `intel.heartbeat.policy`:

    - RED heartbeats every 3 hours (suppressed before, emits after)
    - RED stops after 48 hours
    - RED caps at 16 reminders
    - YELLOW heartbeats every 12 hours
    - YELLOW stops after 48 hours
    - YELLOW caps at 4 reminders
    - GREEN never heartbeats
    - reactivation on material price improvement
    - reactivation on color upgrade
    - reactivation on route / departure / return-date change
    - duplicate suppression by the 5-field fingerprint
    - round-trip combo alerts respect the policy

Runnable directly:
    python tests/test_heartbeat_policy.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.heartbeat import AlertSnapshot  # noqa: E402
from intel.heartbeat.policy import (  # noqa: E402
    combo_heartbeat_color,
    deal_fingerprint,
    decide_policy_heartbeat,
    is_duplicate,
    reactivation_reason,
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


def _decide(color, *, age_h, silence_h, count=0, prev=None, curr=None,
            prev_return=None, curr_return=None):
    """Drive the policy for one observation.

    age_h    = hours since first alert
    silence_h = hours since last heartbeat (None -> never => infinite)
    """
    now = T0 + timedelta(hours=age_h)
    first = T0
    last_hb = now - timedelta(hours=silence_h) if silence_h is not None else None
    base = curr or snap(color=color)
    return decide_policy_heartbeat(
        color=color,
        previous=prev if prev is not None else base,
        current=base,
        first_alert_at=first,
        last_heartbeat_at=last_hb,
        now=now,
        heartbeat_count=count,
        prev_return_date=prev_return,
        curr_return_date=curr_return,
    )


# ---------- RED cadence (every 3 hours) ----------

def test_red_suppressed_before_3h():
    # 2h since last heartbeat, no change -> under the 3h RED interval.
    d = _decide("red", age_h=5, silence_h=2)
    assert d.should_emit is False
    assert "rate-limited" in d.reason


def test_red_emits_at_3h():
    d = _decide("red", age_h=5, silence_h=3)
    assert d.should_emit is True
    assert "RED cadence" in d.reason


def test_red_emits_well_past_interval():
    d = _decide("red", age_h=10, silence_h=5)
    assert d.should_emit is True


# ---------- RED 48h stop ----------

def test_red_stops_after_48h():
    # 49h old, plenty of silence -> stopped, no emit.
    d = _decide("red", age_h=49, silence_h=10)
    assert d.should_emit is False
    assert d.stopped is True
    assert "stopped" in d.reason


def test_red_alive_just_before_48h():
    d = _decide("red", age_h=47.9, silence_h=4)
    assert d.should_emit is True
    assert d.stopped is False


# ---------- RED 16-reminder cap ----------

def test_red_caps_at_16_reminders():
    # 16 reminders already sent, cadence satisfied, no new info -> capped.
    d = _decide("red", age_h=40, silence_h=4, count=16)
    assert d.should_emit is False
    assert d.cap_reached is True
    # One below the cap still emits.
    d2 = _decide("red", age_h=40, silence_h=4, count=15)
    assert d2.should_emit is True


# ---------- YELLOW cadence (every 12 hours) ----------

def test_yellow_suppressed_before_12h():
    d = _decide("yellow", age_h=20, silence_h=6)
    assert d.should_emit is False
    assert "rate-limited" in d.reason


def test_yellow_emits_at_12h():
    d = _decide("yellow", age_h=20, silence_h=12)
    assert d.should_emit is True
    assert "YELLOW cadence" in d.reason


# ---------- YELLOW 48h stop ----------

def test_yellow_stops_after_48h():
    d = _decide("yellow", age_h=49, silence_h=20)
    assert d.should_emit is False
    assert d.stopped is True


# ---------- YELLOW 4-reminder cap ----------

def test_yellow_caps_at_4_reminders():
    d = _decide("yellow", age_h=40, silence_h=13, count=4)
    assert d.should_emit is False
    assert d.cap_reached is True
    d2 = _decide("yellow", age_h=40, silence_h=13, count=3)
    assert d2.should_emit is True


# ---------- GREEN never ----------

def test_green_never_heartbeats():
    d = _decide("green", age_h=1, silence_h=10)
    assert d.should_emit is False
    assert "no heartbeat" in d.reason


def test_green_never_even_with_price_drop():
    # A GREEN deal whose price dropped is still GREEN: no heartbeat.
    prev = snap(color="green", price=300)
    curr = snap(color="green", price=200)
    d = _decide("green", age_h=1, silence_h=10, prev=prev, curr=curr)
    assert d.should_emit is False


def test_unknown_color_never_heartbeats():
    d = _decide("", age_h=1, silence_h=10)
    assert d.should_emit is False


# ---------- reactivation ----------

def test_reactivation_on_material_price_improvement():
    prev = snap(price=300)
    curr = snap(price=270)            # $30 drop
    # Inside the 3h interval AND below... reactivation bypasses both.
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is True
    assert d.is_reactivation is True
    assert "price improved" in d.reason


def test_sub_threshold_price_drop_not_reactivation():
    prev = snap(price=300)
    curr = snap(price=296)            # only $4 -> not material
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is False     # rate-limited, no reactivation
    assert d.is_reactivation is False


def test_price_increase_not_reactivation():
    prev = snap(price=300)
    curr = snap(price=400)            # worse, not an improvement
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is False


def test_reactivation_on_color_upgrade():
    prev = snap(color="yellow")
    curr = snap(color="red")
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is True
    assert d.is_reactivation is True
    assert "color upgrade" in d.reason


def test_color_downgrade_not_reactivation():
    prev = snap(color="red", price=300)
    curr = snap(color="yellow", price=300)
    # Re-observe as YELLOW; downgrade is not a reactivation, and within the
    # 12h YELLOW interval it stays suppressed.
    d = _decide("yellow", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is False
    assert d.is_reactivation is False


def test_reactivation_on_route_change():
    prev = snap(route="BWI->BOG direct")
    curr = snap(route="BWI->MIA->BOG")
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is True and "route" in d.reason


def test_reactivation_on_departure_date_change():
    prev = snap(depart_offset_h=72.0)
    curr = snap(depart_offset_h=72.0 + 24)   # next calendar day
    d = _decide("red", age_h=1, silence_h=0.25, prev=prev, curr=curr)
    assert d.should_emit is True and "departure date" in d.reason


def test_reactivation_on_return_date_change():
    prev = snap()
    curr = snap()
    d = _decide(
        "red", age_h=1, silence_h=0.25, prev=prev, curr=curr,
        prev_return=date(2026, 6, 10), curr_return=date(2026, 6, 14),
    )
    assert d.should_emit is True and "return date" in d.reason


def test_reactivation_bypasses_cap():
    # Capped (16 RED reminders) but a price improvement still emits.
    prev = snap(price=300)
    curr = snap(price=250)
    d = _decide("red", age_h=30, silence_h=4, count=16, prev=prev, curr=curr)
    assert d.should_emit is True
    assert d.is_reactivation is True


def test_reactivation_does_not_bypass_48h_stop():
    # Past the lifetime ceiling even a price improvement does not revive
    # the same deal (only a new deal_id does).
    prev = snap(price=300)
    curr = snap(price=200)
    d = _decide("red", age_h=49, silence_h=4, prev=prev, curr=curr)
    assert d.should_emit is False
    assert d.stopped is True


# ---------- duplicate fingerprint ----------

def test_fingerprint_includes_all_five_fields():
    base = deal_fingerprint("d1", "BWI->BOG", T0, date(2026, 6, 10), 300.0)
    assert deal_fingerprint("d2", "BWI->BOG", T0, date(2026, 6, 10), 300.0) != base
    assert deal_fingerprint("d1", "BWI->MIA->BOG", T0, date(2026, 6, 10), 300.0) != base
    assert deal_fingerprint("d1", "BWI->BOG", T0 + timedelta(days=1), date(2026, 6, 10), 300.0) != base
    assert deal_fingerprint("d1", "BWI->BOG", T0, date(2026, 6, 14), 300.0) != base
    assert deal_fingerprint("d1", "BWI->BOG", T0, date(2026, 6, 10), 305.0) != base
    # Same five fields -> identical fingerprint (a duplicate).
    assert deal_fingerprint("d1", "BWI->BOG", T0, date(2026, 6, 10), 300.0) == base


def test_is_duplicate():
    fp = deal_fingerprint("d1", "BWI->BOG", T0, None, 300.0)
    assert is_duplicate(fp, fp) is True
    assert is_duplicate(None, fp) is False
    other = deal_fingerprint("d1", "BWI->BOG", T0, None, 301.0)
    assert is_duplicate(fp, other) is False


def test_duplicate_is_negation_of_reactivation():
    # Identical fingerprint <=> no reactivation reason.
    prev = snap(price=300)
    curr = snap(price=300)
    assert reactivation_reason(prev, curr) is None
    fp_prev = deal_fingerprint(prev.deal_id, prev.route_signature,
                               prev.departure_at, None, prev.price_usd)
    fp_curr = deal_fingerprint(curr.deal_id, curr.route_signature,
                               curr.departure_at, None, curr.price_usd)
    assert is_duplicate(fp_prev, fp_curr) is True


# ---------- round-trip combos respect the policy ----------

def test_combo_qualifying_colors_map_to_urgency():
    assert combo_heartbeat_color("RED", "RED") == "red"
    assert combo_heartbeat_color("RED", "YELLOW") == "red"      # strongest leg
    assert combo_heartbeat_color("YELLOW", "RED") == "red"
    assert combo_heartbeat_color("YELLOW", "YELLOW") == "yellow"


def test_combo_with_green_or_missing_never_heartbeats():
    assert combo_heartbeat_color("RED", "GREEN") is None
    assert combo_heartbeat_color("GREEN", "YELLOW") is None
    assert combo_heartbeat_color("RED", None) is None
    assert combo_heartbeat_color("", "RED") is None


def test_combo_red_leg_uses_3h_cadence():
    color = combo_heartbeat_color("YELLOW", "RED")     # -> "red"
    # Under 3h -> suppressed; at 3h -> emit. Same as a single RED leg.
    assert _decide(color, age_h=5, silence_h=2).should_emit is False
    assert _decide(color, age_h=5, silence_h=3).should_emit is True


def test_combo_yellow_yellow_uses_12h_cadence():
    color = combo_heartbeat_color("YELLOW", "YELLOW")  # -> "yellow"
    assert _decide(color, age_h=20, silence_h=6).should_emit is False
    assert _decide(color, age_h=20, silence_h=12).should_emit is True


def test_combo_green_never_emits_through_policy():
    color = combo_heartbeat_color("RED", "GREEN")      # -> None
    # A non-qualifying combo carries no heartbeat color; treated as GREEN.
    d = _decide("green" if color is None else color, age_h=1, silence_h=10)
    assert d.should_emit is False


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
    print(f"\nHeartbeat policy: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
