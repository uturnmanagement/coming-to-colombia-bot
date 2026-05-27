"""Layer 2 — live-send validation tests.

Covers:
    - sender wiring (the dispatcher invokes the bound callable)
    - severity gate (RED alerts + heartbeats + system pass; YELLOW/GREEN
      alerts and digests are blocked)
    - dedupe (identical payload inside the window is suppressed)
    - per-deal cooldown (safety floor independent of decay engine)
    - DRY_RUN preservation (no sender call, audit still records)
    - audit log produces one record per send attempt
    - heartbeat suppression still works through dispatcher
    - zombie cutoff still works through dispatcher
    - SCANNER_TELEGRAM_ENABLED=false re-routes scanner calls through
      Oak Street dispatcher with metadata

Runs hermetic — no network calls. The "live" sender is a mock callable.

    python tests/test_layer2_live_send.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.oakstreet import AlertEvent, OakStreet
from db.sqlite_manager import SqliteManager
from links.live_send_audit import LiveSendAuditor
from links.telegram_dispatcher import TelegramDispatcher


T0 = datetime(2026, 5, 27, 10, 0, 0)


def _tmp_audit_path():
    fh = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    fh.close()
    return Path(fh.name)


def _build(
    *,
    dry_run=False,
    cooldown=60,
    dedupe_window=300,
    with_sender=True,
    with_auditor=True,
):
    sender_mock = MagicMock() if with_sender else None
    audit_path = _tmp_audit_path() if with_auditor else None
    dispatcher = TelegramDispatcher(
        bot_token="dummy", chat_id="-1001234567890",
        dry_run=dry_run, sender=sender_mock,
        cooldown_seconds=cooldown, dedupe_window_seconds=dedupe_window,
    )
    if with_auditor:
        dispatcher.attach_auditor(LiveSendAuditor(audit_path))
    db = SqliteManager(db_path=":memory:", dry_run=True)
    oak = OakStreet(db=db, dispatcher=dispatcher)
    return oak, db, dispatcher, sender_mock, audit_path


def _evt(deal_id="d1", color="red", price=300.0,
         route="BWI->BOG direct", age_h=0.0):
    return AlertEvent(
        deal_id=deal_id, color=color, price_usd=price,
        route_signature=route,
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=age_h),
        summary="Test deal",
    )


# ---------- live sender wiring ----------

def test_sender_invoked_on_red_alert():
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="red"))
    sender.assert_called_once()
    assert disp.outbox[-1].outcome == "sent"


def test_sender_not_invoked_in_dry_run():
    oak, _, disp, sender, _ = _build(dry_run=True)
    oak.ingest_alert(_evt(color="red"))
    sender.assert_not_called()
    assert disp.outbox[-1].outcome == "dry_run"
    assert disp.outbox[-1].dry_run is True


# ---------- severity gate ----------

def test_yellow_alert_blocked_by_severity_gate():
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="yellow"))
    sender.assert_not_called()
    assert disp.outbox[-1].outcome == "suppressed_gate"
    assert "below RED" in disp.outbox[-1].reason


def test_green_alert_blocked_by_severity_gate():
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="green"))
    sender.assert_not_called()
    assert disp.outbox[-1].outcome == "suppressed_gate"


def test_digest_blocked_by_severity_gate():
    _, _, disp, sender, _ = _build()
    disp.send("daily roll-up", kind="digest")
    sender.assert_not_called()
    assert disp.outbox[-1].outcome == "suppressed_gate"
    assert "digest" in disp.outbox[-1].reason


def test_system_message_always_passes():
    _, _, disp, sender, _ = _build()
    disp.send("operator status: bot online", kind="system")
    sender.assert_called_once()
    assert disp.outbox[-1].outcome == "sent"


def test_heartbeat_kind_bypasses_color_check():
    """Heartbeats are gated by the decay engine, not the color gate."""
    _, _, disp, sender, _ = _build()
    disp.send("heartbeat body", kind="heartbeat", color="yellow",
              deal_id="d1")
    sender.assert_called_once()
    assert disp.outbox[-1].outcome == "sent"


# ---------- dedupe ----------

def test_identical_payload_inside_window_deduped():
    _, _, disp, sender, _ = _build()
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-A", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=30))
    assert sender.call_count == 1
    assert disp.outbox[-1].outcome == "suppressed_dedupe"


def test_distinct_payload_not_deduped():
    _, _, disp, sender, _ = _build(cooldown=0)  # disable cooldown for this test
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-B", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=30))
    assert sender.call_count == 2


def test_dedupe_window_expires():
    _, _, disp, sender, _ = _build(cooldown=0, dedupe_window=60)
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-A", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=120))
    assert sender.call_count == 2


# ---------- per-deal cooldown ----------

def test_cooldown_suppresses_back_to_back_sends():
    _, _, disp, sender, _ = _build(cooldown=60)
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-B", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=30))
    assert sender.call_count == 1
    assert disp.outbox[-1].outcome == "suppressed_cooldown"
    assert "cooldown" in disp.outbox[-1].reason


def test_cooldown_expires():
    _, _, disp, sender, _ = _build(cooldown=60)
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-B", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=120))
    assert sender.call_count == 2


def test_cooldown_independent_per_deal():
    _, _, disp, sender, _ = _build(cooldown=60)
    disp.send("text-A", kind="system", deal_id="d1", now=T0)
    disp.send("text-B", kind="system", deal_id="d2",
              now=T0 + timedelta(seconds=10))
    assert sender.call_count == 2


# ---------- audit log ----------

def test_audit_log_writes_every_decision():
    _, _, disp, _, audit_path = _build()
    disp.send("p1", kind="system", deal_id="d1", now=T0)
    # Different text to bypass dedupe and reach the cooldown rule.
    disp.send("p2", kind="system", deal_id="d1",
              now=T0 + timedelta(seconds=20))
    disp.send("yellow text", kind="alert", color="yellow",
              deal_id="d2", now=T0 + timedelta(seconds=200))
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    import json
    outcomes = [json.loads(line)["outcome"] for line in lines]
    assert outcomes == ["sent", "suppressed_cooldown", "suppressed_gate"]


def test_audit_records_message_hash_and_length():
    _, _, disp, _, audit_path = _build()
    disp.send("hello world", kind="system")
    import json
    rec = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert rec["text_length"] == len("hello world")
    assert len(rec["text_hash"]) == 16
    assert rec["dry_run"] is False
    assert rec["outcome"] == "sent"


# ---------- Layer 1 preservation through Layer 2 dispatcher ----------

def test_heartbeat_suppression_still_works_through_live_dispatcher():
    """A qualifying heartbeat trigger inside the ACTIVE interval is still
    suppressed by the decay engine before reaching the dispatcher."""
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="red", price=300, age_h=0))
    decision = oak.ingest_alert(
        _evt(color="red", price=320, age_h=10/60)
    )
    assert decision.should_emit is False
    # Only the initial alert reached the dispatcher's sender.
    assert sender.call_count == 1


def test_zombie_cutoff_still_works_through_live_dispatcher():
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="red", price=300, age_h=0))
    decision = oak.ingest_alert(
        _evt(color="red", price=185, age_h=60)
    )
    assert decision.should_emit is False
    assert decision.stage.value == "zombie"
    assert sender.call_count == 1, "zombie must not trigger an additional live send"


def test_heartbeat_path_emits_when_qualifying():
    """A qualifying heartbeat (past interval, material change) does emit
    a live send through the new dispatcher gate."""
    oak, _, disp, sender, _ = _build()
    oak.ingest_alert(_evt(color="red", price=300, age_h=0))
    decision = oak.ingest_alert(_evt(color="red", price=270, age_h=20/60))
    assert decision.should_emit is True
    assert sender.call_count == 2
    assert disp.outbox[-1].kind == "heartbeat"
    assert disp.outbox[-1].outcome == "sent"


# ---------- kill switch + scanner re-routing ----------

def test_scheduler_route_signature_helper():
    """The helper used by src/scheduler.py to feed metadata into the
    dispatcher must produce a stable string for each strategy."""
    from src.scheduler import _route_signature

    class _Rec:
        def __init__(self, strategy, gateway):
            self.strategy = strategy
            self.gateway = gateway

    class _Comp:
        def __init__(self, destination, recommended):
            self.destination = destination
            self.recommended = recommended

    class _Result:
        def __init__(self, destination, strategy, gateway=None):
            self.comparison = _Comp(destination, _Rec(strategy, gateway))

    assert _route_signature(_Result("BOG", "direct")).endswith("BOG")
    assert "direct" in _route_signature(_Result("BOG", "direct"))
    sig = _route_signature(_Result("BOG", "positioning", "MIA"))
    assert "MIA" in sig and "BOG" in sig and "positioning" in sig


def test_desk_config_default_scanner_telegram_enabled():
    """The CODE default must be True — an existing deployment that
    pulls Layer 2 without setting SCANNER_TELEGRAM_ENABLED in its env
    must keep legacy behavior. We patch load_dotenv to a no-op so the
    test observes the documented default of `_env_bool`, not whatever
    the local .env happens to declare today."""
    import os
    from unittest.mock import patch
    from agents.config import load_desk_config

    original = os.environ.pop("SCANNER_TELEGRAM_ENABLED", None)
    try:
        with patch("agents.config.load_dotenv", return_value=False):
            cfg = load_desk_config()
        assert cfg.scanner_telegram_enabled is True
    finally:
        if original is not None:
            os.environ["SCANNER_TELEGRAM_ENABLED"] = original


def test_scanner_send_seam_routes_through_oak_street_when_disabled():
    """When SCANNER_TELEGRAM_ENABLED is false and Oak Street is wired
    into bot_data, the scanner's `_send` calls into the dispatcher
    instead of context.bot.send_message."""
    import asyncio
    from types import SimpleNamespace
    from src.scheduler import _send

    oak, _, disp, sender, _ = _build()
    bot = MagicMock()

    async def _bot_send(**kwargs):
        raise AssertionError("legacy bot send must not be called")
    bot.send_message = _bot_send

    desk_config = SimpleNamespace(scanner_telegram_enabled=False)
    config = SimpleNamespace(telegram_chat_id="-1001234567890")
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "desk_config": desk_config,
            "oakstreet": oak,
            "config": config,
        },
    )
    asyncio.run(_send(
        context, "<b>Colombia Desk RED</b>",
        kind="alert", color="red", deal_id="d-route",
        route_signature="direct->BOG",
    ))
    sender.assert_called_once()
    assert disp.outbox[-1].deal_id == "d-route"
    assert disp.outbox[-1].route_signature == "direct->BOG"


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
    print(f"\nLayer 2 live-send: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
