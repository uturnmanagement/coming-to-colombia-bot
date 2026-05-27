"""Shared Colombia Desk configuration.

Layered on top of the existing src.config (the scanner's region-pack
loader). This module owns orchestration-level settings — DRY_RUN, SQLite
path, Telegram dispatch behavior — that the new agents/intel/links code
reads. The original scanner config is left untouched so its behavior is
preserved bit-for-bit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


REPO_ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


@dataclass(frozen=True)
class DeskConfig:
    """Orchestration-level settings.

    DRY_RUN suppresses all outbound side effects (Telegram sends, SQLite
    writes are buffered in memory only). The scanner's own behavior is
    unaffected — DRY_RUN gates the new dispatch layer, not the existing
    scanner.
    """
    dry_run: bool
    sqlite_path: Path
    logs_dir: Path
    telegram_bot_token: str
    telegram_chat_id: str
    log_level: str

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_desk_config() -> DeskConfig:
    load_dotenv()
    logs_dir = REPO_ROOT / "logs"
    db_dir = REPO_ROOT / "db"
    return DeskConfig(
        dry_run=_env_bool("DRY_RUN", default=False),
        sqlite_path=Path(_env("COLOMBIA_DESK_DB", str(db_dir / "colombia_desk.sqlite"))),
        logs_dir=logs_dir,
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        log_level=_env("LOG_LEVEL", "INFO").upper(),
    )
