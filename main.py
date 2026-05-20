"""Entry point for the OpsHub Global Airfare Intelligence System.

Loads the active region pack, wires the flight fetcher, storage, the
heartbeat manager, Telegram handlers, and the job scheduler, then runs
the bot with long polling.

Run locally:  python main.py
Pick a market with REGION_PACK in .env (colombia, europe, japan, ...).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.error import Conflict, InvalidToken, NetworkError
from telegram.ext import Application, Defaults

from src.config import load_config
from src.flight_fetcher import LiveFlightFetcher, get_fetcher
from src.heartbeat_alerts import HeartbeatManager
from src.scheduler import setup_jobs
from src.storage import Storage
from src.telegram_handlers import register_handlers

LOG_DIR = Path(__file__).resolve().parent / "logs"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "airfare.log", encoding="utf-8"),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def _on_start(application: Application) -> None:
    """Runs once the bot is initialized — confirms it is live and polling."""
    log = logging.getLogger("airfare")
    try:
        me = await application.bot.get_me()
        log.info("=" * 52)
        log.info("AIRFARE INTELLIGENCE BOT ONLINE AND POLLING")
        log.info("Bot: @%s  (id %s)", me.username, me.id)
        log.info("=" * 52)
    except Exception:
        log.exception("post_init get_me() failed")


async def _on_error(update: object, context) -> None:
    """Central error handler — keeps polling alive and labels conflicts."""
    err = context.error
    log = logging.getLogger("airfare")
    if isinstance(err, Conflict):
        log.error("BOT ALREADY RUNNING IN ANOTHER SESSION — %s", err)
    elif isinstance(err, NetworkError):
        log.warning("Network error (will retry): %s", err)
    else:
        log.error("Unhandled error: %s", err, exc_info=err)


def main() -> None:
    _setup_logging()
    log = logging.getLogger("airfare")

    config = load_config()
    problems = config.validate()
    if problems:
        log.error("Configuration problems found:")
        for problem in problems:
            log.error("  - %s", problem)
        log.error("Fix your .env / region pack and restart.")
        sys.exit(1)

    log.info("Region pack: %s (%s)", config.region.name, config.region_pack)

    try:
        tz = ZoneInfo(config.timezone)
    except Exception:
        log.warning("Unknown timezone %r — falling back to UTC", config.timezone)
        tz = ZoneInfo("UTC")

    fetcher = get_fetcher(config)
    if isinstance(fetcher, LiveFlightFetcher):
        ok, message = fetcher.verify_connection()
        if ok:
            log.info(
                "Live flight provider '%s' active — %s",
                config.flight_api_provider, message,
            )
        else:
            log.warning("%s — bot will run on placeholder fallback", message)
    else:
        log.info(
            "Flight data source: placeholder fallback (provider=%s)",
            config.flight_api_provider,
        )

    storage = Storage(LOG_DIR)
    heartbeat = HeartbeatManager(config, fetcher, storage)

    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .defaults(Defaults(tzinfo=tz))
        .post_init(_on_start)
        .build()
    )
    application.bot_data.update(
        {
            "config": config,
            "fetcher": fetcher,
            "storage": storage,
            "heartbeat": heartbeat,
            "latest_results": [],
            "last_scan_at": None,
        }
    )

    register_handlers(application)
    application.add_error_handler(_on_error)
    setup_jobs(application, config)

    log.info("Airfare Intelligence starting — %s", config.summary())
    try:
        application.run_polling(drop_pending_updates=True)
    except InvalidToken:
        log.error("INVALID TELEGRAM TOKEN")
        sys.exit(1)
    except Conflict:
        log.error("BOT ALREADY RUNNING IN ANOTHER SESSION")
        sys.exit(1)


if __name__ == "__main__":
    main()
