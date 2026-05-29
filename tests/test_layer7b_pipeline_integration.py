"""Layer 7B — pipeline integration tests.

Covers the full scan_job -> ingest_alert -> specialists -> dispatch_briefing
wiring, all hermetic and DRY_RUN-safe:

    - fake scan context routing (_emit_red -> pipeline vs legacy _send)
    - fake alert ingestion (first observation registers + dispatches)
    - specialist execution (delta/echo/india reports cached)
    - briefing generation (named sections rendered)
    - dispatch simulation (DRY_RUN: outbox + audit, sender never called)
    - heartbeat parity (pipeline decisions == direct ingest_alert)
    - specialist isolation (a broken specialist is skipped, not fatal)

Runnable directly:
    python tests/test_layer7b_pipeline_integration.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.scheduler as sched
from agents.oakstreet import AlertEvent, OakStreet
from agents.oakstreet.pipeline import DeskPipeline
from agents.specialist_report import SpecialistReport, Status
from db.sqlite_manager import SqliteManager
from intel.lodging import LodgingIntelService, LodgingStorage
from intel.lodging.providers import MockLodgingProvider
from links.live_send_audit import LiveSendAuditor
from links.telegram_dispatcher import TelegramDispatcher


T0 = datetime(2026, 5, 28, 12, 0, 0)


def _tmp_audit() -> Path:
    fh = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    fh.close()
    return Path(fh.name)


def _oak(dry_run=True):
    sender = MagicMock()
    db = SqliteManager(db_path=":memory:", dry_run=True)
    disp = TelegramDispatcher(
        bot_token="dummy", chat_id="-1001234567890",
        dry_run=dry_run, sender=sender,
        cooldown_seconds=0, dedupe_window_seconds=0,
    )
    audit = _tmp_audit()
    disp.attach_auditor(LiveSendAuditor(audit))
    return OakStreet(db=db, dispatcher=disp), disp, sender, audit


def _lodging_service():
    mgr = SqliteManager(":memory:", dry_run=True)
    svc = LodgingIntelService(
        storage=LodgingStorage(mgr), providers=[MockLodgingProvider()],
        lookback_days=14,
    )
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    return svc


def _event(deal_id="d-7b", price=285.0, color="red", observed_at=T0):
    return AlertEvent(
        deal_id=deal_id, color=color, price_usd=price,
        route_signature="direct->BOG",
        departure_at=T0 + timedelta(hours=72),
        observed_at=observed_at,
        summary="BWI->BOG $285",
    )


# ---------- specialist execution + briefing generation ----------

def test_pipeline_runs_all_specialists_and_briefs():
    oak, disp, sender, _ = _oak()
    pipe = DeskPipeline(oakstreet=oak, lodging_service=_lodging_service())
    res = pipe.process_event(_event())
    assert res.decision is None              # first observation
    assert set(res.reports) == {"delta", "echo", "india"}
    assert res.briefing_text is not None
    for token in ("DELTA", "ECHO", "INDIA"):
        assert token in res.briefing_text
    assert not res.specialist_errors


# ---------- dispatch simulation (DRY_RUN) ----------

def test_dry_run_outbox_and_audit_no_live_send():
    oak, disp, sender, audit = _oak(dry_run=True)
    pipe = DeskPipeline(oakstreet=oak, lodging_service=_lodging_service())
    pipe.process_event(_event())
    sender.assert_not_called()                       # NO live send
    kinds = [m.kind for m in disp.outbox]
    assert "alert" in kinds and "heartbeat" in kinds  # initial + briefing
    assert all(m.outcome == "dry_run" for m in disp.outbox)
    rows = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) >= 2
    assert all(json.loads(r)["outcome"] == "dry_run" for r in rows)


# ---------- heartbeat parity ----------

def test_heartbeat_parity_second_observation():
    """Routing through the pipeline must not change the decay decision."""
    p_oak, *_ = _oak()
    d_oak, *_ = _oak()
    pipe = DeskPipeline(oakstreet=p_oak, lodging_service=None)

    ev1 = _event(observed_at=T0)
    ev2 = _event(price=250.0, observed_at=T0 + timedelta(minutes=20))

    # First obs both sides => None
    assert pipe.process_event(ev1).decision is None
    assert d_oak.ingest_alert(ev1) is None

    p_dec = pipe.process_event(ev2).decision
    d_dec = d_oak.ingest_alert(ev2)
    assert p_dec is not None and d_dec is not None
    assert p_dec.stage == d_dec.stage
    assert p_dec.should_emit == d_dec.should_emit


def test_heartbeat_parity_zombie_suppression():
    p_oak, *_ = _oak()
    d_oak, *_ = _oak()
    pipe = DeskPipeline(oakstreet=p_oak, lodging_service=None)

    ev1 = _event(observed_at=T0)
    zombie = _event(price=180.0, observed_at=T0 + timedelta(hours=70))

    pipe.process_event(ev1)
    d_oak.ingest_alert(ev1)

    p_dec = pipe.process_event(zombie).decision
    d_dec = d_oak.ingest_alert(zombie)
    assert p_dec.stage == d_dec.stage          # both ZOMBIE
    assert p_dec.should_emit is d_dec.should_emit is False


# ---------- specialist isolation ----------

def test_broken_specialist_does_not_abort_pipeline():
    oak, disp, sender, _ = _oak()

    class _Boom:
        def analyze(self, event):
            raise RuntimeError("specialist down")

    from agents.echo import Echo
    pipe = DeskPipeline(oakstreet=oak, specialists=[_Boom(), Echo({"BOG": 330.0})])
    res = pipe.process_event(_event())
    assert "echo" in res.reports                 # good one still ran
    assert res.specialist_errors                  # bad one recorded
    assert res.briefing_text is not None          # briefing still produced
    sender.assert_not_called()


# ---------- fake scan context routing ----------

class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


class _FakeContext:
    def __init__(self, bot_data):
        self.bot = _FakeBot()
        self.bot_data = bot_data


class _RecordingPipeline:
    def __init__(self):
        self.events = []

    def process_event(self, event, **_):
        self.events.append(event)
        return None


def test_emit_red_routes_to_pipeline_when_killswitch_off():
    pipe = _RecordingPipeline()
    ctx = _FakeContext({
        "desk_pipeline": pipe,
        "desk_config": SimpleNamespace(scanner_telegram_enabled=False),
        "config": object(),
    })
    saved = sched._event_from_result
    sched._event_from_result = lambda result, config: "EVENT"
    try:
        asyncio.run(sched._emit_red(ctx, result=object(), key="k"))
        assert pipe.events == ["EVENT"]
        assert ctx.bot.sent == []                 # no live send path taken
    finally:
        sched._event_from_result = saved


def test_emit_red_falls_back_to_send_without_pipeline():
    sent = []

    async def fake_send(context, text, **kw):
        sent.append(kw)

    saved = (sched._send, sched.format_deal_alert, sched._route_signature)
    sched._send = fake_send
    sched.format_deal_alert = lambda r: "ALERT"
    sched._route_signature = lambda r: "direct->BOG"
    try:
        ctx = _FakeContext({
            "desk_config": SimpleNamespace(scanner_telegram_enabled=False),
        })
        asyncio.run(sched._emit_red(ctx, result=object(), key="k"))
        assert len(sent) == 1 and sent[0]["kind"] == "alert"
    finally:
        sched._send, sched.format_deal_alert, sched._route_signature = saved


def test_emit_red_killswitch_on_uses_legacy_even_with_pipeline():
    pipe = _RecordingPipeline()
    sent = []

    async def fake_send(context, text, **kw):
        sent.append(kw)

    saved = (sched._send, sched.format_deal_alert, sched._route_signature)
    sched._send = fake_send
    sched.format_deal_alert = lambda r: "ALERT"
    sched._route_signature = lambda r: "direct->BOG"
    try:
        ctx = _FakeContext({
            "desk_pipeline": pipe,
            "desk_config": SimpleNamespace(scanner_telegram_enabled=True),
        })
        asyncio.run(sched._emit_red(ctx, result=object(), key="k"))
        assert pipe.events == []                   # legacy path, not pipeline
        assert len(sent) == 1
    finally:
        sched._send, sched.format_deal_alert, sched._route_signature = saved


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
    print(f"\nLayer 7B pipeline integration: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
