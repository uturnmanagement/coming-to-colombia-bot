"""Phase 2.7 — round-trip combo logic tests.

Proves:
    - the four QUALIFYING combos (both legs >= YELLOW) classify correctly,
    - the non-qualifying pairings (any leg GREEN / missing) do NOT qualify,
    - the Delta optimizer payload carries combo fields end to end.

Runnable directly:
    python tests/test_round_trip_combo.py
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intel.return_pairing import (
    COMBO_CATEGORIES,
    combo_color,
    qualifies,
)
from agents.delta import Delta
from agents.oakstreet import AlertEvent


# ---------- Task 4: combinations that MUST qualify ----------

def test_qualifying_red_red():
    assert combo_color("RED", "RED") == "RED_RED"
    assert qualifies("RED", "RED") is True


def test_qualifying_red_yellow():
    assert combo_color("RED", "YELLOW") == "RED_YELLOW"
    assert qualifies("RED", "YELLOW") is True


def test_qualifying_yellow_red():
    assert combo_color("YELLOW", "RED") == "YELLOW_RED"
    assert qualifies("YELLOW", "RED") is True


def test_qualifying_yellow_yellow():
    assert combo_color("YELLOW", "YELLOW") == "YELLOW_YELLOW"
    assert qualifies("YELLOW", "YELLOW") is True


def test_all_qualifying_categories_are_known():
    for ob in ("RED", "YELLOW"):
        for rt in ("RED", "YELLOW"):
            c = combo_color(ob, rt)
            assert c in COMBO_CATEGORIES
            assert c != "NON_QUALIFYING"


# ---------- Task 5: combinations that must NOT qualify ----------

def test_non_qualifying_green_yellow():
    assert combo_color("GREEN", "YELLOW") == "NON_QUALIFYING"
    assert qualifies("GREEN", "YELLOW") is False


def test_non_qualifying_yellow_green():
    assert combo_color("YELLOW", "GREEN") == "NON_QUALIFYING"
    assert qualifies("YELLOW", "GREEN") is False


def test_non_qualifying_green_green():
    assert combo_color("GREEN", "GREEN") == "NON_QUALIFYING"
    assert qualifies("GREEN", "GREEN") is False


def test_non_qualifying_red_green():
    assert combo_color("RED", "GREEN") == "NON_QUALIFYING"
    assert qualifies("RED", "GREEN") is False


def test_non_qualifying_green_red():
    assert combo_color("GREEN", "RED") == "NON_QUALIFYING"
    assert qualifies("GREEN", "RED") is False


# ---------- robustness: case / missing ----------

def test_combo_is_case_insensitive():
    assert combo_color("red", "yellow") == "RED_YELLOW"
    assert qualifies("yellow", "red") is True


def test_missing_or_unknown_colors_do_not_qualify():
    for bad in (None, "", "BLUE", "  "):
        assert combo_color(bad, "RED") == "NON_QUALIFYING"
        assert combo_color("RED", bad) == "NON_QUALIFYING"
        assert qualifies(bad, "RED") is False


# ---------- integration: combo fields flow through Delta ----------

T0 = datetime(2026, 5, 27, 10, 0, 0)
COMBO_KEYS = {
    "outbound_color", "return_color", "combo_color", "qualifies",
    "round_trip_typical_usd", "savings_vs_typical_usd",
}


def _event(color: str, price: float = 285.0) -> AlertEvent:
    return AlertEvent(
        deal_id=f"DEAL-{color}",
        color=color,
        price_usd=price,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary=f"BWI->BOG ${price:.0f}",
    )


def _spread_fetcher(_a, _b, when: date):
    """Deterministic return prices that force a RED/YELLOW/GREEN spread."""
    d = when.day
    if d <= 8:
        return 100.0      # cheapest -> colors RED
    if d <= 15:
        return 150.0      # -> YELLOW
    if d <= 22:
        return 300.0      # -> GREEN
    return 330.0          # -> GREEN


def test_delta_payload_options_carry_combo_fields():
    rpt = Delta(fetcher=_spread_fetcher, windows=(7, 14, 21, 30)).analyze(_event("red"))
    opts = rpt.payload["options"]
    assert opts, "expected priced options"
    for o in opts:
        assert COMBO_KEYS.issubset(o), f"missing combo keys: {COMBO_KEYS - set(o)}"
        # combo_color must equal the pure function over the same colors.
        assert o["combo_color"] == combo_color(rpt.payload["outbound_color"], o["return_color"])
        assert o["qualifies"] == qualifies(rpt.payload["outbound_color"], o["return_color"])


def test_delta_counts_qualifying_combos_for_red_outbound():
    rpt = Delta(fetcher=_spread_fetcher, windows=(7, 14, 21, 30)).analyze(_event("red"))
    opts = rpt.payload["options"]
    expected = sum(1 for o in opts if o["qualifies"])
    assert rpt.payload["qualifying_count"] == expected
    assert rpt.payload["qualifying_count"] >= 1, "RED outbound + spread must yield combos"
    # best_qualifying is the cheapest qualifying round trip.
    bq = rpt.payload["best_qualifying"]
    assert bq is not None and bq["qualifies"] is True
    cheapest_q = min((o for o in opts if o["qualifies"]),
                     key=lambda o: o["round_trip_total_usd"])
    assert bq["round_trip_total_usd"] == cheapest_q["round_trip_total_usd"]
    assert "round-trip-combo" in rpt.flags


def test_delta_green_outbound_never_qualifies():
    rpt = Delta(fetcher=_spread_fetcher, windows=(7, 14, 21, 30)).analyze(_event("green"))
    assert rpt.payload["qualifying_count"] == 0
    assert rpt.payload["best_qualifying"] is None
    assert all(o["combo_color"] == "NON_QUALIFYING" for o in rpt.payload["options"])
    assert "round-trip-combo" not in rpt.flags


def test_delta_yellow_outbound_qualifies_on_yellow_or_red_returns():
    rpt = Delta(fetcher=_spread_fetcher, windows=(7, 14, 21, 30)).analyze(_event("yellow"))
    cats = {o["combo_color"] for o in rpt.payload["options"] if o["qualifies"]}
    assert cats, "YELLOW outbound should qualify on RED/YELLOW returns"
    assert cats <= {"YELLOW_RED", "YELLOW_YELLOW"}


if __name__ == "__main__":  # direct-run convenience
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failures = []
    for fn in fns:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{fn.__name__}: {exc!r}")
    print(f"ran {len(fns)} tests, {len(failures)} failed")
    for f in failures:
        print("  FAIL", f)
    sys.exit(1 if failures else 0)
