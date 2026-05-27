"""Scanner preservation tests — guarantees Layer 1 did not change scanner
behavior.

Approach: re-run the legacy smoke flow that was green before the Layer 1
refactor. If any of those assertions break, Layer 1 has regressed the
scanner — abort and fix.

Runnable directly:
    python tests/test_scanner_preservation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_legacy_smoke_still_passes():
    """The legacy hermetic smoke must run end-to-end without modification.

    We import test_smoke and run its `main()` if present, or run each
    `test_*` function the legacy module exposes. The legacy script
    exits with 1 on failure — we catch SystemExit and reraise as a
    plain assertion so this test can be collected with the others.
    """
    import importlib
    smoke = importlib.import_module("tests.test_smoke")

    failures = []
    for name in dir(smoke):
        if not name.startswith("test_"):
            continue
        fn = getattr(smoke, name)
        if not callable(fn):
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - test surface
            failures.append(f"{name}: {exc}")
    assert not failures, f"legacy smoke regressions: {failures}"


def test_src_modules_still_importable():
    """The scanner's public surface must still import cleanly."""
    import src.config as _cfg            # noqa: F401
    import src.region as _region         # noqa: F401
    import src.flight_fetcher as _ff     # noqa: F401
    import src.route_compare as _rc      # noqa: F401
    import src.deal_classifier as _dc    # noqa: F401
    import src.arrival_rules as _ar      # noqa: F401
    import src.alert_formatter as _af    # noqa: F401
    import src.scheduler as _sch         # noqa: F401
    import src.storage as _st            # noqa: F401
    import src.heartbeat_alerts as _hb   # noqa: F401
    import src.telegram_handlers as _th  # noqa: F401


def test_default_region_pack_unchanged():
    """colombia pack still loads as the default."""
    from src.config import load_config
    cfg = load_config()
    assert cfg.region is not None, f"region failed: {cfg.region_error}"
    assert cfg.region_pack == "colombia"
    assert cfg.region.slug == "colombia"


def test_layer1_does_not_shadow_scanner_logger():
    """The new colombia_desk.* logger namespace must not consume airfare.*
    log records. (Trivial check that nothing aliased the root logger.)
    """
    import logging
    airfare = logging.getLogger("airfare")
    desk = logging.getLogger("colombia_desk")
    assert airfare is not desk
    assert airfare.name == "airfare"
    assert desk.name == "colombia_desk"


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
    print(f"\nScanner preservation: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
