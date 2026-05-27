"""Oak Street skeleton tests.

Asserts:
    - first observation registers a deal and sends an alert
    - re-observation under rate limit -> dispatcher unchanged
    - re-observation past rate limit + material change -> heartbeat emit
    - zombie deal -> no emission, status flipped
    - specialist report ingestion writes to the placeholder table

Runnable directly:
    python tests/test_oakstreet_skeleton.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.oakstreet import AlertEvent, OakStreet  # noqa: E402
from db.sqlite_manager import SqliteManager        # noqa: E402
from links.telegram_dispatcher import TelegramDispatcher  # noqa: E402


T0 = datetime(2026, 5, 26, 10, 0, 0)


def _setup():
    db = SqliteManager(db_path=":memory:", dry_run=True)
    disp = TelegramDispatcher(
        bot_token="dummy", chat_id="dummy_chat", dry_run=True,
    )
    oak = OakStreet(db=db, dispatcher=disp)
    return oak, db, disp


def _evt(deal_id="d1", color="red", price=300.0, route="BWI->BOG direct",
         age_h=0.0, first=False):
    return AlertEvent(
        deal_id=deal_id,
        color=color,
        price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=age_h),
        summary="Test deal",
        is_first_observation=first,
    )


def test_first_alert_registers_and_sends():
    oak, db, disp = _setup()
    decision = oak.ingest_alert(_evt(first=True))
    assert decision is None, "first observation skips heartbeat decision"
    assert len(disp.outbox) == 1
    assert disp.outbox[0].kind == "alert"
    row = db.get_deal("d1")
    assert row is not None
    assert row["status"] == "active"
    assert row["heartbeat_count"] == 0


def test_rate_limited_observation_suppresses():
    oak, db, disp = _setup()
    oak.ingest_alert(_evt(first=True))
    # 10 minutes later — under ACTIVE 15-min interval, even with a
    # qualifying price jump.
    decision = oak.ingest_alert(_evt(price=400, age_h=10/60))
    assert decision is not None
    assert decision.should_emit is False
    assert len(disp.outbox) == 1, "no heartbeat should be emitted"


def test_material_change_after_interval_emits_heartbeat():
    oak, db, disp = _setup()
    oak.ingest_alert(_evt(first=True))
    # 20 min later, $20 drop -> beyond ACTIVE 15-min interval.
    decision = oak.ingest_alert(_evt(price=270, age_h=20/60))
    assert decision is not None and decision.should_emit is True
    assert disp.outbox[-1].kind == "heartbeat"
    row = db.get_deal("d1")
    assert row["heartbeat_count"] == 1
    snaps = db.snapshots_for("d1")
    assert len(snaps) == 1
    assert snaps[0]["trigger_reason"].startswith("material change")


def test_zombie_mutes():
    oak, db, disp = _setup()
    oak.ingest_alert(_evt(first=True))
    # Same deal observed 72h later -> ZOMBIE.
    decision = oak.ingest_alert(_evt(price=400, age_h=72))
    assert decision is not None
    assert decision.should_emit is False
    assert decision.stage.value == "zombie"
    assert len(disp.outbox) == 1, "no heartbeat emitted in zombie"
    row = db.get_deal("d1")
    assert row["status"] == "zombie"


def test_specialist_report_persisted():
    oak, db, _ = _setup()
    oak.ingest_alert(_evt(first=True))
    oak.ingest_specialist_report(
        specialist="echo",
        payload={"note": "weather looks fine"},
        deal_id="d1",
        now=T0 + timedelta(minutes=5),
    )
    reports = db.specialist_reports_for("d1")
    assert len(reports) == 1
    assert reports[0]["specialist"] == "echo"
    assert "weather" in reports[0]["payload_json"]


def test_dispatcher_dry_run_marks_messages():
    oak, _, disp = _setup()
    oak.ingest_alert(_evt(first=True))
    assert all(m.dry_run for m in disp.outbox), "DRY_RUN must flag every send"


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
    print(f"\nOak Street skeleton: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
