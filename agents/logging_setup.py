"""Centralized logging for Colombia Desk.

One log file (`logs/colombia_desk.log`) plus stdout. All new modules use
loggers under the `colombia_desk.*` namespace. The existing scanner's
`airfare.*` loggers are not touched.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_ROOT = "colombia_desk"
_CONFIGURED = False


def setup_logging(logs_dir: Path, level: str = "INFO") -> logging.Logger:
    """Idempotent — safe to call from every entry point."""
    global _CONFIGURED
    root = logging.getLogger(LOGGER_ROOT)
    if _CONFIGURED:
        return root

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "colombia_desk.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)

    root.setLevel(getattr(logging, level, logging.INFO))
    root.addHandler(fh)
    root.addHandler(sh)
    root.propagate = False

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """`get_logger("heartbeat")` → logger `colombia_desk.heartbeat`."""
    return logging.getLogger(f"{LOGGER_ROOT}.{name}")
