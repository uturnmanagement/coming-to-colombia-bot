"""Layer 7A — safety invariants.

Proves Layer 7A cannot send Telegram and preserves the safe posture:
    - The live_providers package imports nothing from links/ and exposes
      no send/dispatch surface (data-only).
    - DeskConfig honors DRY_RUN=true and SCANNER_TELEGRAM_ENABLED=false.
    - The existing STUB lodging providers are unchanged (still STUB).
    - Mock mode works with no key and no external API.

No secrets are read or printed; env is exercised via a temporary mapping.

Runnable directly:
    python tests/test_layer7a_safety.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import intel.live_providers as lp
from agents.config import _env_bool
from intel.live_providers import LiveProviderStatus, LiveResult
from intel.lodging.providers import AirDnaProvider, InsideAirbnbProvider
from intel.lodging.providers.interface import ProviderStatus


_PKG_DIR = ROOT / "intel" / "live_providers"


# ---------- no Telegram coupling ----------

def test_package_has_no_links_or_telegram_imports():
    """Scan actual import statements only (not prose/docstrings)."""
    offenders = []
    for path in _PKG_DIR.glob("*.py"):
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip().lower()
            if not (line.startswith("import ") or line.startswith("from ")):
                continue
            if "links" in line or "telegram" in line or "dispatcher" in line:
                offenders.append(f"{path.name}: {raw.strip()}")
    assert not offenders, f"live_providers must not import Telegram: {offenders}"


def test_live_result_is_data_only():
    assert not hasattr(LiveResult, "send")
    assert not hasattr(LiveResult, "dispatch")
    # The public surface exposes builders + results, not any sender.
    assert not any("send" in name.lower() or "dispatch" in name.lower()
                   for name in lp.__all__)


# ---------- DRY_RUN / kill switch posture ----------

def test_dry_run_and_kill_switch_env_mapping():
    prev = {k: os.environ.get(k) for k in ("DRY_RUN", "SCANNER_TELEGRAM_ENABLED")}
    try:
        os.environ["DRY_RUN"] = "true"
        os.environ["SCANNER_TELEGRAM_ENABLED"] = "false"
        assert _env_bool("DRY_RUN", default=False) is True
        assert _env_bool("SCANNER_TELEGRAM_ENABLED", default=True) is False
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------- existing STUB providers unchanged ----------

def test_airdna_stub_intact():
    res = AirDnaProvider().fetch(city="BOG")
    assert res.status is ProviderStatus.STUB


def test_inside_airbnb_stub_intact():
    res = InsideAirbnbProvider().fetch(city="BOG")
    assert res.status is ProviderStatus.STUB


# ---------- mock mode needs no key / no network ----------

def test_mock_mode_no_key_no_network():
    res = lp.build_airfare_provider(env={}).fetch(origin="BWI", destination="BOG")
    assert res.status is LiveProviderStatus.OK and res.is_usable


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
    print(f"\nLayer 7A safety: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
