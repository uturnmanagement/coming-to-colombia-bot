"""Job scheduling: regular scans, RED heartbeat, daily digest.

Registers jobs on the python-telegram-bot JobQueue. Destinations come
from the active region pack, so the scan covers whatever market the
framework is configured for.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from . import region
from .alert_formatter import format_daily_summary, format_deal_alert
from .deal_classifier import DealColor, classify_route
from .route_compare import compare_routes
from .storage import make_deal_key

log = logging.getLogger("airfare.scheduler")


def _scan_day(config):
    return datetime.now().date() + timedelta(days=config.scan_days_ahead)


async def _send(context, text: str) -> None:
    config = context.bot_data["config"]
    await context.bot.send_message(
        chat_id=config.telegram_chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def run_full_scan(bot_data: dict) -> list:
    """Pure scan: build a ranked DealResult list for every destination."""
    config = bot_data["config"]
    fetcher = bot_data["fetcher"]
    day = _scan_day(config)
    results = []
    for dest in region.destination_codes():
        comparison = compare_routes(fetcher, dest, config, day)
        results.append(classify_route(comparison, config))
    results.sort(key=lambda r: r.classification.urgency_score, reverse=True)
    return results


async def scan_job(context) -> None:
    """Scheduled scan: refresh deals, alert YELLOW/RED, arm heartbeats."""
    data = context.bot_data
    storage = data["storage"]
    heartbeat = data["heartbeat"]
    try:
        results = run_full_scan(data)
    except Exception:  # keep the bot alive on a bad scan
        log.exception("scan failed")
        return

    data["latest_results"] = results
    data["last_scan_at"] = datetime.now()
    try:
        storage.record_scan(results, data["last_scan_at"])
    except Exception:
        log.exception("failed to persist scan")

    reds = yellows = 0
    for result in results:
        color = result.color
        if color == DealColor.GREEN:
            continue
        key = make_deal_key(result)
        if color == DealColor.RED:
            reds += 1
            newly_armed = heartbeat.register(result.destination)
            if newly_armed or not storage.was_alerted(key):
                await _send(context, format_deal_alert(result))
                storage.mark_alerted(key)
        elif color == DealColor.YELLOW:
            yellows += 1
            if not storage.was_alerted(key):
                await _send(context, format_deal_alert(result))
                storage.mark_alerted(key)
    log.info(
        "scan complete: %d deals (%d red, %d yellow)", len(results), reds, yellows
    )


async def heartbeat_job(context) -> None:
    """RED heartbeat pulse — no-op when nothing is being tracked."""
    heartbeat = context.bot_data["heartbeat"]
    if heartbeat.active_count() == 0:
        return

    async def send(text: str) -> None:
        await _send(context, text)

    try:
        await heartbeat.tick(send)
    except Exception:
        log.exception("heartbeat tick failed")


async def daily_summary_job(context) -> None:
    """GREEN daily digest of every destination."""
    data = context.bot_data
    results = data.get("latest_results")
    if not results:
        try:
            results = run_full_scan(data)
            data["latest_results"] = results
            data["last_scan_at"] = datetime.now()
        except Exception:
            log.exception("daily summary scan failed")
            return
    scan_time = data.get("last_scan_at") or datetime.now()
    await _send(context, format_daily_summary(results, scan_time))


def setup_jobs(application, config) -> None:
    """Register all recurring jobs on the application's JobQueue."""
    jq = application.job_queue
    if jq is None:
        raise RuntimeError(
            "JobQueue unavailable — install python-telegram-bot[job-queue]."
        )
    jq.run_once(scan_job, when=5, name="initial-scan")
    jq.run_repeating(
        scan_job,
        interval=timedelta(minutes=config.yellow_recheck_minutes),
        first=timedelta(minutes=config.yellow_recheck_minutes),
        name="recheck-scan",
    )
    jq.run_repeating(
        heartbeat_job,
        interval=timedelta(minutes=config.red_heartbeat_minutes),
        first=timedelta(minutes=config.red_heartbeat_minutes),
        name="red-heartbeat",
    )
    jq.run_daily(
        daily_summary_job,
        time=time(hour=config.green_summary_hour, minute=0),
        name="daily-summary",
    )
    log.info(
        "jobs registered: recheck=%dm heartbeat=%dm summary=%02d:00",
        config.yellow_recheck_minutes,
        config.red_heartbeat_minutes,
        config.green_summary_hour,
    )
