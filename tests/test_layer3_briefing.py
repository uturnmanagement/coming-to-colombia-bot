"""Layer 3 — Oak Street ingestion + briefing synthesis tests.

Covers:
    - typed ingest_report rejects wrong types
    - ingest_report persists to the specialist_reports table
    - synthesize_briefing returns None with no reports
    - synthesize_briefing combines Delta + Echo into one body
    - dispatch_briefing routes through the dispatcher with kind='heartbeat'
    - DRY_RUN still suppresses live wire on briefing dispatch
    - briefing render survives the dispatcher's severity gate
    - L1/L2 invariants intact: heartbeat suppression, zombie cutoff,
      audit recording, DRY_RUN

Runnable directly:
    python tests/test_layer3_briefing.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.delta import Delta
from agents.echo import Echo
from agents.oakstreet import AlertEvent, OakStreet, SpecialistReport, Status
from db.sqlite_manager import SqliteManager
from links.live_send_audit import LiveSendAuditor
from links.telegram_dispatcher import TelegramDispatcher


T0 = datetime(2026, 5, 27, 10, 0, 0)


def _tmp_audit() -> Path:
    fh = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    fh.close()
    return Path(fh.name)


def _build(dry_run=True, with_sender=True):
    sender = MagicMock() if with_sender else None
    db = SqliteManager(db_path=":memory:", dry_run=True)
    disp = TelegramDispatcher(
        bot_token="dummy", chat_id="-1001234567890",
        dry_run=dry_run, sender=sender,
        cooldown_seconds=0, dedupe_window_seconds=0,
    )
    audit_path = _tmp_audit()
    disp.attach_auditor(LiveSendAuditor(audit_path))
    oak = OakStreet(db=db, dispatcher=disp)
    return oak, db, disp, sender, audit_path


def _event(deal_id="d-brief", price=285.0):
    return AlertEvent(
        deal_id=deal_id,
        color="red",
        price_usd=price,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


# ---------- ingest_report ----------

def test_ingest_report_rejects_non_specialist_type():
    oak, *_ = _build()
    try:
        oak.ingest_report({"agent": "delta"})  # plain dict — wrong shape
    except TypeError:
        return
    raise AssertionError("ingest_report must reject non-SpecialistReport input")


def test_ingest_report_persists_to_specialist_reports_table():
    oak, db, *_ = _build()
    oak.ingest_alert(_event())
    rpt = Delta().analyze(_event())
    oak.ingest_report(rpt)
    persisted = db.specialist_reports_for("d-brief")
    assert len(persisted) == 1
    assert persisted[0]["specialist"] == "delta"
    payload = json.loads(persisted[0]["payload_json"])
    assert payload["agent"] == "delta"
    assert "options" in payload["payload"]


def test_ingest_report_caches_in_memory():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    cached = oak._reports_cache.get("d-brief")
    assert cached is not None
    assert set(cached.keys()) == {"delta", "echo"}


# ---------- briefing synthesis ----------

def test_synthesize_briefing_returns_none_without_reports():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    assert oak.synthesize_briefing("d-brief") is None


def test_synthesize_briefing_combines_delta_and_echo():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event(price=200)))
    text = oak.synthesize_briefing("d-brief", now=T0 + timedelta(minutes=1))
    assert text is not None
    assert "DELTA" in text
    assert "return pairing" in text
    assert "ECHO" in text
    assert "price context" in text
    assert "great" in text or "good" in text or "normal" in text or "high" in text
    assert "internal briefing" in text


def test_synthesize_briefing_with_unknown_specialist():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    other = SpecialistReport(
        agent="india",
        status=Status.STUB,
        confidence=0.3,
        deal_id="d-brief",
        observed_at=T0,
        payload={"note": "future hook"},
        flags=(),
        verdict_input={},
    )
    oak.ingest_report(other)
    text = oak.synthesize_briefing("d-brief")
    assert "INDIA" in text
    assert "stub" in text


# ---------- dispatch_briefing + DRY_RUN ----------

def test_dispatch_briefing_dry_run_does_not_send_live():
    oak, _, disp, sender, audit_path = _build(dry_run=True)
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    text = oak.dispatch_briefing(
        "d-brief", color="red",
        route_signature="BWI->BOG direct",
        now=T0 + timedelta(minutes=2),
    )
    assert text is not None
    sender.assert_not_called()
    # Both an alert (from ingest_alert) and the briefing should be in outbox.
    briefing_msg = disp.outbox[-1]
    assert briefing_msg.kind == "heartbeat"
    assert briefing_msg.outcome == "dry_run"
    # Audit log contains the briefing decision too.
    audit_rows = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(audit_rows) >= 2
    last = json.loads(audit_rows[-1])
    assert last["kind"] == "heartbeat"
    assert last["outcome"] == "dry_run"


def test_dispatch_briefing_returns_none_when_no_reports():
    oak, _, disp, sender, _ = _build(dry_run=True)
    oak.ingest_alert(_event())
    text = oak.dispatch_briefing("d-brief", color="red",
                                 route_signature="BWI->BOG direct")
    assert text is None
    # Only the initial alert is in the outbox; no briefing was emitted.
    assert len(disp.outbox) == 1


# ---------- Layer 1 / Layer 2 invariants intact through Layer 3 ----------

def test_heartbeat_suppression_intact_with_specialist_reports():
    oak, *_ = _build(dry_run=True)
    oak.ingest_alert(_event(price=300))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-brief", color="red", price_usd=320,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(minutes=10),  # inside 15-min ACTIVE
        summary="follow-up",
    ))
    assert decision.should_emit is False
    assert "rate-limited" in decision.reason or "no material change" in decision.reason


def test_zombie_cutoff_intact_with_specialist_reports():
    oak, *_ = _build(dry_run=True)
    oak.ingest_alert(_event(price=300))
    # Specialist reports cached, deal aged to zombie.
    oak.ingest_report(Delta().analyze(_event()))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-brief", color="red", price_usd=180,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=60),  # 60h → zombie
        summary="zombie attempt",
    ))
    assert decision.should_emit is False
    assert decision.stage.value == "zombie"


def test_dispatcher_audit_records_briefing_metadata():
    """Verifies the audit JSONL carries deal_id + kind on a briefing
    dispatch — the foundation Layer 4 audit analyzer needs."""
    oak, _, disp, _, audit_path = _build(dry_run=True)
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    oak.dispatch_briefing(
        "d-brief", color="red",
        route_signature="BWI->BOG direct",
    )
    rows = [json.loads(line) for line in
            audit_path.read_text(encoding="utf-8").strip().splitlines()]
    briefing = rows[-1]
    assert briefing["deal_id"] == "d-brief"
    assert briefing["kind"] == "heartbeat"
    assert briefing["color"] == "red"
    assert briefing["route_signature"] == "BWI->BOG direct"


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
    print(f"\nLayer 3 briefing: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
