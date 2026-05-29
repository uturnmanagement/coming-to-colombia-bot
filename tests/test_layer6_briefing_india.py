"""Layer 6 — Oak Street briefing renderer tests (India section + Echo
lodging line).

Covers:
    - India now renders as a dedicated '<b>INDIA · ...</b>' section
      (best option, price, score, options considered)
    - India is no longer emitted via the generic unknown-specialist
      fall-through line
    - Backward compatibility: an india report with a future-hook payload
      (no 'signal') still renders 'INDIA' and echoes its status ('stub')
    - Echo's lodging line renders the live signal when wired, and
      'not available' when unwired
    - Section ordering stays deterministic: DELTA, ECHO, INDIA
    - Frozen invariant: DRY_RUN dispatch with India present never sends

Runnable directly:
    python tests/test_layer6_briefing_india.py
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
from agents.india import India
from agents.oakstreet import AlertEvent, OakStreet, SpecialistReport, Status
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


def _build(dry_run=True):
    sender = MagicMock()
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


def _event(deal_id="d-brief6", price=285.0):
    return AlertEvent(
        deal_id=deal_id, color="red", price_usd=price,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary="BWI->BOG $285",
    )


def _lodging_service() -> LodgingIntelService:
    mgr = SqliteManager(":memory:", dry_run=True)
    svc = LodgingIntelService(
        storage=LodgingStorage(mgr),
        providers=[MockLodgingProvider()],
        lookback_days=14,
    )
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    return svc


# ---------- India dedicated section ----------

def test_india_renders_dedicated_section():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(India(lodging_service=_lodging_service()).analyze(_event()))
    text = oak.synthesize_briefing("d-brief6", now=T0 + timedelta(minutes=1))
    assert "INDIA · hostels and budget stays" in text
    assert "best:" in text
    assert "options considered:" in text


def test_india_not_in_generic_fallthrough():
    """The generic fall-through uses 'NAME — status=...'; India must not
    use that shape any more."""
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(India(lodging_service=_lodging_service()).analyze(_event()))
    text = oak.synthesize_briefing("d-brief6", now=T0 + timedelta(minutes=1))
    assert "INDIA — status=" not in text


def test_india_future_hook_payload_backward_compatible():
    """Mirrors the Layer 3 unknown-specialist test: an india report with
    no 'signal' must still render INDIA and echo its status."""
    oak, *_ = _build()
    oak.ingest_alert(_event())
    other = SpecialistReport(
        agent="india", status=Status.STUB, confidence=0.3,
        deal_id="d-brief6", observed_at=T0,
        payload={"note": "future hook"}, flags=(), verdict_input={},
    )
    oak.ingest_report(other)
    text = oak.synthesize_briefing("d-brief6")
    assert "INDIA" in text
    assert "stub" in text
    assert "no scored options for city" in text


# ---------- Echo lodging line ----------

def test_echo_lodging_line_when_wired():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    echo = Echo(
        {"BOG": 330.0},
        lodging_service=_lodging_service(),
        lodging_observed_usd=20.0,
    ).analyze(_event())
    oak.ingest_report(echo)
    text = oak.synthesize_briefing("d-brief6", now=T0 + timedelta(minutes=1))
    assert "lodging signal:" in text
    assert "not available" not in text
    assert "below typical" in text


def test_echo_lodging_line_when_unwired():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    text = oak.synthesize_briefing("d-brief6", now=T0 + timedelta(minutes=1))
    assert "lodging signal: <i>not available</i>" in text


# ---------- ordering ----------

def test_section_order_delta_echo_india():
    oak, *_ = _build()
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    oak.ingest_report(India(lodging_service=_lodging_service()).analyze(_event()))
    text = oak.synthesize_briefing("d-brief6", now=T0 + timedelta(minutes=1))
    i_delta = text.find("DELTA")
    i_echo = text.find("ECHO")
    i_india = text.find("INDIA")
    assert -1 < i_delta < i_echo < i_india


# ---------- frozen invariant: DRY_RUN with India present ----------

def test_dry_run_dispatch_with_india_does_not_send():
    oak, _, disp, sender, audit_path = _build(dry_run=True)
    oak.ingest_alert(_event())
    oak.ingest_report(India(lodging_service=_lodging_service()).analyze(_event()))
    text = oak.dispatch_briefing(
        "d-brief6", color="red",
        route_signature="BWI->BOG direct",
        now=T0 + timedelta(minutes=2),
    )
    assert text is not None
    sender.assert_not_called()
    last = json.loads(
        audit_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert last["kind"] == "heartbeat"
    assert last["outcome"] == "dry_run"


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
    print(f"\nLayer 6 briefing India: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
