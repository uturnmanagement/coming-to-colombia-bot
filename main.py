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

# Layer 2 — Colombia Desk orchestration wiring. The legacy scanner above
# still runs unchanged; Oak Street layers on top through bot_data so the
# scanner's `_send` can re-route through it when the kill switch is off.
from agents.config import load_desk_config
from agents.logging_setup import setup_logging as setup_desk_logging
from agents.oakstreet import OakStreet
from agents.oakstreet.pipeline import DeskPipeline
from db.sqlite_manager import SqliteManager
from intel.lodging import LodgingIntelService, LodgingStorage
from intel.lodging.providers import MockLodgingProvider
from links.live_send_audit import LiveSendAuditor
from links.telegram_dispatcher import TelegramDispatcher

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

    # --- Colombia Desk / Oak Street wiring (Layer 2) ------------------
    desk_config = load_desk_config()
    setup_desk_logging(desk_config.logs_dir, level=desk_config.log_level)
    desk_db = SqliteManager(
        db_path=desk_config.sqlite_path, dry_run=desk_config.dry_run
    )
    auditor = LiveSendAuditor(desk_config.audit_log_path)
    dispatcher = TelegramDispatcher(
        bot_token=desk_config.telegram_bot_token,
        chat_id=desk_config.telegram_chat_id,
        dry_run=desk_config.dry_run,
        cooldown_seconds=desk_config.live_send_cooldown_seconds,
    )
    dispatcher.attach_auditor(auditor)
    oakstreet = OakStreet(db=desk_db, dispatcher=dispatcher)

    # Layer 7B — desk pipeline: ingest_alert -> specialists -> briefing.
    # India consults a mock-backed lodging brain (hermetic, no network).
    # DRY_RUN keeps every dispatch record-only until live arming (7C).
    lodging_service = None
    if desk_config.lodging_intel_enabled:
        lodging_service = LodgingIntelService(
            storage=LodgingStorage(desk_db),
            providers=[MockLodgingProvider()],
            lookback_days=desk_config.lodging_baseline_lookback_days,
        )
    desk_pipeline = DeskPipeline(
        oakstreet=oakstreet, lodging_service=lodging_service
    )
    # ------------------------------------------------------------------

    application = (
        Application.builder()
        .token(config.telegram_bot_token)
        .defaults(Defaults(tzinfo=tz))
        .post_init(_on_start)
        .build()
    )

    def _bot_sender(chat_id: str, text: str) -> None:
        """Live Telegram send via the running PTB application bot.

        Fire-and-forget: the coroutine is scheduled on the running
        application event loop via `Application.create_task`. We do
        not await — the dispatcher's caller is often a sync code path
        (Oak Street simulations) and the dispatcher's interface is
        synchronous. Send failures propagate to the application's
        central error handler (`_on_error`) which logs them; the
        dispatcher's audit log records `outcome="sent"` at the
        scheduling moment.
        """
        application.create_task(
            application.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML",
                disable_web_page_preview=True,
            )
        )

    dispatcher.sender = _bot_sender

    application.bot_data.update(
        {
            "config": config,
            "fetcher": fetcher,
            "storage": storage,
            "heartbeat": heartbeat,
            "latest_results": [],
            "last_scan_at": None,
            # Layer 2 wiring — exposed to src.scheduler._send.
            "desk_config": desk_config,
            "oakstreet": oakstreet,
            # Layer 7B wiring — exposed to src.scheduler._emit_red.
            "desk_pipeline": desk_pipeline,
        }
    )

    log.info(
        "Colombia Desk wired: scanner_telegram_enabled=%s dry_run=%s "
        "live_send_cooldown=%ds",
        desk_config.scanner_telegram_enabled,
        desk_config.dry_run,
        desk_config.live_send_cooldown_seconds,
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
