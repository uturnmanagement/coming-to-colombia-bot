"""Layer 5 — Layer 1/2/3/4 protections still pass + no live Telegram.

Covers:
    - India never touches the dispatcher (no Telegram side effects)
    - Oak Street ingest_report accepts India's SpecialistReport
    - synthesize_briefing renders INDIA alongside DELTA + ECHO
    - dispatch_briefing under DRY_RUN records outcome='dry_run'
    - Heartbeat suppression and zombie cutoff still hold
    - Layer 4 Echo lodging_signal still None (Layer 5 ships India only)
    - Layer 3 schema rejects unknown verdict_input keys (regression
      protection on the VERDICT_KEYS extension)
    - No live Telegram path can fire while India runs alongside

Runnable directly:
    python tests/test_layer5_india_protections.py
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

from agents.delta import Delta
from agents.echo import Echo
from agents.india import India
from agents.oakstreet import AlertEvent, OakStreet
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


def _stack(dry_run=True):
    mgr = SqliteManager(":memory:", dry_run=True)
    sender = MagicMock()
    disp = TelegramDispatcher(
        bot_token="dummy", chat_id="-100123",
        dry_run=dry_run, sender=sender,
        cooldown_seconds=0, dedupe_window_seconds=0,
    )
    disp.attach_auditor(LiveSendAuditor(_tmp_audit()))
    oak = OakStreet(db=mgr, dispatcher=disp)
    lodging_svc = LodgingIntelService(
        storage=LodgingStorage(mgr),
        providers=[MockLodgingProvider()],
        lookback_days=14,
    )
    return mgr, oak, disp, sender, lodging_svc


def _event(deal_id="d-l5", price=285.0):
    return AlertEvent(
        deal_id=deal_id, color="red", price_usd=price,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0, summary="BWI->BOG $285",
    )


# ---------- India never sends ----------

def test_india_does_not_touch_dispatcher():
    _, _, disp, sender, lodging = _stack()
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    India(lodging_service=lodging).analyze(_event())
    sender.assert_not_called()
    assert disp.outbox == []


# ---------- Oak Street typed ingest accepts India ----------

def test_oakstreet_ingests_india_specialist_report():
    _, oak, _, _, lodging = _stack()
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event())
    report = India(lodging_service=lodging).analyze(_event())
    assert isinstance(report, SpecialistReport)
    oak.ingest_report(report)
    cached = oak._reports_cache.get("d-l5")
    assert cached is not None
    assert "india" in cached


def test_synthesize_briefing_includes_india_section():
    _, oak, _, _, lodging = _stack()
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    oak.ingest_report(India(lodging_service=lodging).analyze(_event()))
    text = oak.synthesize_briefing("d-l5", now=T0 + timedelta(minutes=1))
    assert text is not None
    # DELTA + ECHO are named renderers; INDIA is the unknown-specialist
    # fall-through and appears as a single line.
    assert "DELTA" in text
    assert "ECHO" in text
    assert "INDIA" in text


def test_dispatch_briefing_with_india_stays_dry_run():
    _, oak, disp, sender, lodging = _stack(dry_run=True)
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    oak.ingest_report(India(lodging_service=lodging).analyze(_event()))
    text = oak.dispatch_briefing(
        "d-l5", color="red", route_signature="BWI->BOG direct",
        now=T0 + timedelta(minutes=2),
    )
    assert text is not None
    sender.assert_not_called()
    assert disp.outbox[-1].outcome == "dry_run"


# ---------- L1 protections through L5 ----------

def test_heartbeat_suppression_intact_with_india():
    _, oak, _, _, lodging = _stack(dry_run=True)
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event(price=300))
    oak.ingest_report(India(lodging_service=lodging).analyze(_event(price=300)))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-l5", color="red", price_usd=320,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(minutes=10),
        summary="follow-up",
    ))
    assert decision.should_emit is False


def test_zombie_cutoff_intact_with_india():
    _, oak, _, _, lodging = _stack(dry_run=True)
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event(price=300))
    oak.ingest_report(India(lodging_service=lodging).analyze(_event(price=300)))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-l5", color="red", price_usd=180,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=60),
        summary="zombie attempt",
    ))
    assert decision.should_emit is False
    assert decision.stage.value == "zombie"


# ---------- L4 Echo still ships lodging_signal=None ----------

def test_echo_lodging_signal_still_none_after_layer5():
    """Layer 5 wires India, NOT Echo. Echo's reserved slot stays None."""
    rpt = Echo({"BOG": 330.0}).analyze(_event())
    assert rpt.verdict_input["lodging_signal"] is None
    assert rpt.payload["lodging_signal"] is None


# ---------- VERDICT_KEYS strict-validation regression guard ----------

def test_unknown_verdict_key_still_rejected():
    """The Layer 3 schema must still reject unknown keys after Layer 5
    extended VERDICT_KEYS. Belt-and-suspenders on the extension point."""
    try:
        SpecialistReport(
            agent="india", status=Status.OK, confidence=0.5,
            deal_id="d-x", observed_at=T0, payload={},
            flags=(), verdict_input={"made_up_key": 1},
        )
    except ValueError:
        return
    raise AssertionError("unknown verdict_input keys must still raise")


# ---------- No live Telegram can fire ----------

def test_no_live_telegram_path_with_india_active():
    _, oak, disp, sender, lodging = _stack(dry_run=True)
    lodging.refresh_observations(city="BOG", now=T0)
    lodging.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event())
    oak.ingest_report(India(lodging_service=lodging).analyze(_event()))
    oak.dispatch_briefing(
        "d-l5", color="red", route_signature="BWI->BOG direct",
        now=T0 + timedelta(minutes=1),
    )
    outcomes = {m.outcome for m in disp.outbox}
    assert outcomes == {"dry_run"}
    sender.assert_not_called()


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
    print(f"\nLayer 5 India protections: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
