"""Phase 6A — lodging-appendix pipeline integration tests.

Proves the mock lodging price appendix is wired into the LIVE briefing
path (DeskPipeline -> OakStreet.synthesize_briefing), gated by
LODGING_APPENDIX_ENABLED, and is fully defensive. Hermetic and
DRY_RUN-safe: no network, no live sends.

Covers:
    - supported destination city  -> appendix block present in briefing
    - unsupported destination city -> appendix omitted (briefing intact)
    - gate off (default)           -> appendix omitted even for a city
    - the appendix never aborts a briefing (other sections still render)

The appendix is the ONLY producer of a <pre> block in a briefing, so
its presence/absence is asserted on "<pre>" unambiguously (the Echo /
India "lodging signal" lines are lowercase prose, not <pre>).

Runnable directly:
    python tests/test_lodging_appendix_pipeline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.oakstreet import AlertEvent, OakStreet
from agents.oakstreet.pipeline import DeskPipeline
from db.sqlite_manager import SqliteManager
from links.live_send_audit import LiveSendAuditor
from links.telegram_dispatcher import TelegramDispatcher

T0 = datetime(2026, 5, 28, 12, 0, 0)
_GATE = "LODGING_APPENDIX_ENABLED"


def _tmp_audit() -> Path:
    fh = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    fh.close()
    return Path(fh.name)


def _oak():
    sender = MagicMock()
    db = SqliteManager(db_path=":memory:", dry_run=True)
    disp = TelegramDispatcher(
        bot_token="dummy", chat_id="-1001234567890",
        dry_run=True, sender=sender,
        cooldown_seconds=0, dedupe_window_seconds=0,
    )
    disp.attach_auditor(LiveSendAuditor(_tmp_audit()))
    return OakStreet(db=db, dispatcher=disp), sender


def _event(dest_code: str, deal_id: str | None = None) -> AlertEvent:
    return AlertEvent(
        deal_id=deal_id or f"d-{dest_code}",
        color="red",
        price_usd=285.0,
        route_signature=f"direct->{dest_code}",
        departure_at=T0 + timedelta(hours=72),
        observed_at=T0,
        summary=f"BWI->{dest_code} $285",
    )


@contextmanager
def _gate(value: str | None):
    """Set/clear LODGING_APPENDIX_ENABLED for the duration, then restore."""
    saved = os.environ.get(_GATE)
    if value is None:
        os.environ.pop(_GATE, None)
    else:
        os.environ[_GATE] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop(_GATE, None)
        else:
            os.environ[_GATE] = saved


def _brief(dest_code: str) -> str:
    oak, sender = _oak()
    pipe = DeskPipeline(oakstreet=oak, lodging_service=None)
    res = pipe.process_event(_event(dest_code))
    sender.assert_not_called()              # DRY_RUN: never a live send
    assert res.briefing_text is not None    # briefing always produced
    return res.briefing_text


# ---------- supported city: appendix present ----------

def test_supported_city_shows_lodging_appendix():
    with _gate("true"):
        text = _brief("MDE")               # Medellín — in the 15-city registry
    assert "<pre>" in text and "</pre>" in text         # appendix block present
    assert "LODGING · accommodation estimates" in text  # appendix header
    assert "Medellín" in text                           # rendered city table
    assert "DELTA" in text                              # other sections intact


# ---------- unsupported city: appendix omitted ----------

def test_unsupported_city_omits_lodging_appendix():
    with _gate("true"):
        text = _brief("JFK")               # not a Colombia desk city
    assert "<pre>" not in text             # NO appendix block
    assert "LODGING · accommodation estimates" not in text
    assert "DELTA" in text                 # briefing otherwise intact


# ---------- gate off (default): appendix omitted even for a city ----------

def test_gate_off_omits_appendix_for_supported_city():
    with _gate("false"):
        text_false = _brief("MDE")
    with _gate(None):                      # var absent -> default off
        text_absent = _brief("MDE")
    for text in (text_false, text_absent):
        assert "<pre>" not in text
        assert "LODGING · accommodation estimates" not in text
        assert "DELTA" in text             # briefing still rendered


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
    print(f"\nLodging appendix pipeline: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
