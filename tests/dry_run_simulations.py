"""Layer 1 DRY_RUN simulations.

Four scenarios exercised end-to-end (Oak Street + heartbeat engine +
SQLite + Telegram dispatcher), with every Telegram send and SQLite
write fully simulated:

    1. RED alert            — first observation, dispatcher records alert
    2. Heartbeat suppression — qualifying change, but rate-limited
    3. Heartbeat trigger     — qualifying change past interval
    4. Zombie cutoff         — 48h+ deal, every change muted

Each scenario prints the rendered Telegram body so the operator can
verify "one voice" output before any live wiring.

Run:
    python tests/dry_run_simulations.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force UTF-8 stdout on Windows so the rendered Telegram emoji print
# cleanly under cp1252 / cp437 default console codepages.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from agents.oakstreet import AlertEvent, OakStreet
from db.sqlite_manager import SqliteManager
from links.telegram_dispatcher import TelegramDispatcher


T0 = datetime(2026, 5, 26, 10, 0, 0)


def _fresh_oak():
    db = SqliteManager(db_path=":memory:", dry_run=True)
    disp = TelegramDispatcher(
        bot_token="DRY", chat_id="DRY_CHAT", dry_run=True,
    )
    return OakStreet(db=db, dispatcher=disp), db, disp


def _evt(deal_id, color, price, route, age_h, summary):
    return AlertEvent(
        deal_id=deal_id,
        color=color,
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=age_h),
        summary=summary,
        is_first_observation=(age_h == 0.0),
    )


def banner(title):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def scenario_red_alert():
    banner("SCENARIO 1 — RED alert (first observation)")
    oak, db, disp = _fresh_oak()
    oak.ingest_alert(
        _evt("BOG-RED-001", "red", 285, "BWI->BOG direct", 0.0,
             "BWI->BOG direct, $285 — $145 below typical")
    )
    sent = disp.outbox[-1]
    print(f"dispatched kind={sent.kind} dry_run={sent.dry_run}")
    print("---rendered message---")
    print(sent.text)
    print("---deals row---")
    print(db.get_deal("BOG-RED-001"))


def scenario_heartbeat_suppression():
    banner("SCENARIO 2 — heartbeat suppression (rate-limited)")
    oak, db, disp = _fresh_oak()
    oak.ingest_alert(
        _evt("BOG-RED-002", "red", 285, "BWI->BOG direct", 0.0,
             "BWI->BOG direct, $285")
    )
    # 10 minutes later — $30 drop. ACTIVE stage but inside 15-min interval.
    decision = oak.ingest_alert(
        _evt("BOG-RED-002", "red", 255, "BWI->BOG direct", 10/60,
             "BWI->BOG direct, $255")
    )
    print(f"second observation emitted? {decision.should_emit}")
    print(f"stage: {decision.stage.value}")
    print(f"reason: {decision.reason}")
    print(f"outbox size: {len(disp.outbox)} (expect 1 — alert only, no heartbeat)")


def scenario_heartbeat_trigger():
    banner("SCENARIO 3 — heartbeat trigger (material change past interval)")
    oak, db, disp = _fresh_oak()
    oak.ingest_alert(
        _evt("BOG-RED-003", "red", 285, "BWI->BOG direct", 0.0,
             "BWI->BOG direct, $285")
    )
    # 20 min later, $30 drop -> beyond ACTIVE 15-min interval, $5 trigger met.
    decision = oak.ingest_alert(
        _evt("BOG-RED-003", "red", 255, "BWI->BOG direct", 20/60,
             "BWI->BOG direct, $255")
    )
    print(f"emitted? {decision.should_emit}")
    print(f"reason: {decision.reason}")
    sent = disp.outbox[-1]
    print(f"dispatched kind={sent.kind} dry_run={sent.dry_run}")
    print("---rendered heartbeat---")
    print(sent.text)
    row = db.get_deal("BOG-RED-003")
    print(f"heartbeat_count={row['heartbeat_count']} status={row['status']}")
    snaps = db.snapshots_for("BOG-RED-003")
    print(f"snapshots: {len(snaps)} (expect 1)")


def scenario_zombie_cutoff():
    banner("SCENARIO 4 — zombie cutoff (48h+)")
    oak, db, disp = _fresh_oak()
    oak.ingest_alert(
        _evt("BOG-RED-004", "red", 285, "BWI->BOG direct", 0.0,
             "BWI->BOG direct, $285")
    )
    # 60h later — clear price drop ($100). Must still NOT emit.
    decision = oak.ingest_alert(
        _evt("BOG-RED-004", "red", 185, "BWI->BOG direct", 60.0,
             "BWI->BOG direct, $185 — dramatic drop")
    )
    print(f"emitted? {decision.should_emit}")
    print(f"stage: {decision.stage.value}")
    print(f"reason: {decision.reason}")
    row = db.get_deal("BOG-RED-004")
    print(f"status after observation: {row['status']}")
    print(f"outbox size: {len(disp.outbox)} (expect 1 — alert only)")


def main():
    print("Colombia Desk — Layer 1 DRY_RUN simulations")
    print(f"Base time: {T0.isoformat()}")
    scenario_red_alert()
    scenario_heartbeat_suppression()
    scenario_heartbeat_trigger()
    scenario_zombie_cutoff()
    print()
    print("All simulations completed (no network, no disk writes).")


if __name__ == "__main__":
    main()
