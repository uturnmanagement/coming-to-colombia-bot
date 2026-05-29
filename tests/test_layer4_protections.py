"""Layer 4 — Layer 1/2/3 protections still pass + no live Telegram sends.

Covers:
    - End-to-end LodgingIntelService.signal_for() returns a typed
      LodgingSignal without ever touching the dispatcher.
    - LODGING_INTEL_ENABLED=false short-circuits even with providers
      present.
    - Echo's verdict_input still carries lodging_signal=None (Layer 4
      ships the brain only — Echo wiring is reserved).
    - Oak Street ingest_alert + ingest_report + dispatch_briefing path
      stays DRY_RUN-suppressed under Layer 4.
    - Heartbeat decay engine still suppresses; zombie still mutes.
    - Dispatcher's outbox shows kind/outcome correctly while running
      Layer 4 alongside the Oak Street briefing.
    - desk_config carries every Layer 4 field with documented defaults.

Runnable directly:
    python tests/test_layer4_protections.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.delta import Delta
from agents.echo import Echo
from agents.oakstreet import AlertEvent, OakStreet
from db.sqlite_manager import SqliteManager
from intel.lodging import (
    LodgingColor,
    LodgingIntelService,
    LodgingStorage,
    LodgingThresholds,
)
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
    storage = LodgingStorage(mgr)
    svc = LodgingIntelService(
        storage=storage,
        providers=[MockLodgingProvider()],
        lookback_days=14,
    )
    return mgr, oak, disp, sender, svc


def _event(deal_id="d-l4", price=285.0):
    return AlertEvent(
        deal_id=deal_id, color="red", price_usd=price,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0, summary="BWI->BOG $285",
    )


# ---------- LodgingIntelService is hermetic ----------

def test_signal_for_returns_typed_signal_after_refresh_and_baseline():
    _, _, _, _, svc = _stack()
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    sig = svc.signal_for(
        observed_usd=40.0, city="BOG", on_date=date(2026, 7, 4),  # HIGH
    )
    assert sig is not None
    assert sig.baseline_price_usd > 0
    assert sig.sample_size > 0
    assert sig.color in (LodgingColor.GREEN, LodgingColor.YELLOW, LodgingColor.RED)


def test_signal_for_returns_none_when_disabled():
    _, _, _, _, svc = _stack()
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    svc.enabled = False
    assert svc.signal_for(observed_usd=40.0, city="BOG") is None


def test_signal_for_returns_none_when_no_baseline_yet():
    _, _, _, _, svc = _stack()
    # No refresh, no baseline.
    assert svc.signal_for(observed_usd=40.0, city="BOG") is None


def test_lodging_service_never_touches_dispatcher():
    """The brain is the brain. It cannot send messages."""
    _, _, disp, sender, svc = _stack()
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    svc.signal_for(observed_usd=40.0, city="BOG")
    sender.assert_not_called()
    # The dispatcher's outbox should be empty — nothing was sent.
    assert disp.outbox == []


# ---------- Echo still ships lodging_signal=None in Layer 4 ----------

def test_echo_lodging_signal_remains_none_in_layer4():
    """Layer 4 is the brain only. Echo's verdict_input["lodging_signal"]
    stays None until the Echo->LodgingIntelService wiring happens in a
    later layer."""
    rpt = Echo({"BOG": 330.0}).analyze(_event())
    assert rpt.verdict_input["lodging_signal"] is None
    assert rpt.payload["lodging_signal"] is None
    assert "lodging-hook-reserved" in rpt.flags


# ---------- Oak Street path still DRY_RUN-suppressed alongside Layer 4 ----------

def test_oakstreet_briefing_dry_run_suppressed_with_lodging_service_present():
    _, oak, disp, sender, svc = _stack(dry_run=True)
    # Build lodging context.
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    # Run the Oak Street alert + briefing path.
    oak.ingest_alert(_event())
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    text = oak.dispatch_briefing(
        "d-l4", color="red", route_signature="BWI->BOG direct",
        now=T0 + timedelta(minutes=2),
    )
    assert text is not None
    # DRY_RUN was respected — sender never invoked even though Lodging
    # Intel was busy in the same process.
    sender.assert_not_called()
    last = disp.outbox[-1]
    assert last.outcome == "dry_run"
    assert last.kind == "heartbeat"


# ---------- Heartbeat suppression + zombie cutoff intact ----------

def test_heartbeat_suppression_intact_with_layer4_active():
    _, oak, disp, sender, svc = _stack(dry_run=True)
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event(price=300))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-l4", color="red", price_usd=320,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(minutes=10),
        summary="follow-up",
    ))
    assert decision.should_emit is False


def test_zombie_cutoff_intact_with_layer4_active():
    _, oak, _, _, svc = _stack(dry_run=True)
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event(price=300))
    decision = oak.ingest_alert(AlertEvent(
        deal_id="d-l4", color="red", price_usd=180,
        route_signature="BWI->BOG direct",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0 + timedelta(hours=60),  # 60h → zombie
        summary="zombie attempt",
    ))
    assert decision.should_emit is False
    assert decision.stage.value == "zombie"


# ---------- DeskConfig wiring ----------

def test_desk_config_documented_defaults():
    """When no Layer 4 env vars are set, the defaults from the spec apply."""
    overridden = [
        "LODGING_INTEL_ENABLED", "AIRDNA_API_KEY",
        "INSIDE_AIRBNB_LOCAL_PATH", "LODGING_YELLOW_THRESHOLD",
        "LODGING_RED_THRESHOLD", "LODGING_SEASON_WEIGHTING",
        "LODGING_BASELINE_LOOKBACK_DAYS",
    ]
    snapshot = {k: os.environ.pop(k, None) for k in overridden}
    try:
        from agents.config import load_desk_config
        with patch("agents.config.load_dotenv", return_value=False):
            cfg = load_desk_config()
        assert cfg.lodging_intel_enabled is True
        assert cfg.airdna_api_key == ""
        assert cfg.inside_airbnb_local_path == "/data/insideairbnb"
        assert cfg.lodging_yellow_threshold_pct == 8.0
        assert cfg.lodging_red_threshold_pct == 15.0
        assert cfg.lodging_season_weighting is True
        assert cfg.lodging_baseline_lookback_days == 90
    finally:
        for k, v in snapshot.items():
            if v is not None:
                os.environ[k] = v


def test_lodging_intel_disabled_via_env():
    from agents.config import load_desk_config

    original = os.environ.get("LODGING_INTEL_ENABLED")
    os.environ["LODGING_INTEL_ENABLED"] = "false"
    try:
        with patch("agents.config.load_dotenv", return_value=False):
            cfg = load_desk_config()
        assert cfg.lodging_intel_enabled is False
    finally:
        if original is None:
            os.environ.pop("LODGING_INTEL_ENABLED", None)
        else:
            os.environ["LODGING_INTEL_ENABLED"] = original


# ---------- No live Telegram path can fire ----------

def test_no_live_telegram_path_can_fire_under_layer4():
    """Every dispatcher.send under DRY_RUN=true must report outcome
    'dry_run' regardless of Layer 4 activity."""
    _, oak, disp, sender, svc = _stack(dry_run=True)
    svc.refresh_observations(city="BOG", now=T0)
    svc.build_baseline(city="BOG", now=T0)
    oak.ingest_alert(_event())
    # Force a few extra dispatcher sends via Oak Street briefing.
    oak.ingest_report(Delta().analyze(_event()))
    oak.ingest_report(Echo({"BOG": 330.0}).analyze(_event()))
    oak.dispatch_briefing(
        "d-l4", color="red", route_signature="BWI->BOG direct",
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
    print(f"\nLayer 4 protections: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
