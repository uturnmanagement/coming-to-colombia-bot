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


def _route_signature(result) -> str | None:
    """Stable route-signature string for the dispatcher's dedupe layer."""
    rec = result.comparison.recommended
    if rec is None:
        return f"{result.comparison.destination}<-none"
    if rec.strategy == "direct":
        return f"direct->{result.comparison.destination}"
    gateway = rec.gateway or "?"
    return f"positioning->{gateway}->{result.comparison.destination}"


async def _send(context, text: str, *, kind: str = "alert",
                color: str | None = None, deal_id: str | None = None,
                route_signature: str | None = None) -> None:
    """Outbound Telegram seam for the scanner.

    Layer 2 wiring:
      - When the kill switch `desk_config.scanner_telegram_enabled` is
        False, the direct `context.bot.send_message` path is suppressed.
      - If Oak Street is wired into bot_data, the suppressed send is
        re-routed through its dispatcher (severity gate + dedupe +
        cooldown + audit). If Oak Street is not wired, the message is
        dropped silently — only the audit logger (if attached) records.
      - When the kill switch is True (default), legacy behavior is
        preserved bit-for-bit: direct send via the PTB application bot.
    """
    data = context.bot_data
    desk_config = data.get("desk_config")
    oak = data.get("oakstreet")

    if desk_config is not None and not desk_config.scanner_telegram_enabled:
        if oak is not None:
            oak.dispatcher.send(
                text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature,
            )
        else:
            log.info(
                "scanner Telegram send suppressed by SCANNER_TELEGRAM_ENABLED=false "
                "and Oak Street is not wired (kind=%s color=%s)", kind, color,
            )
        return

    config = data["config"]
    await context.bot.send_message(
        chat_id=config.telegram_chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def _event_from_result(result, config):
    """Build an Oak Street AlertEvent from a scanner DealResult.

    Lazy import keeps src/ free of a top-level agents dependency (the
    scanner must remain importable on its own). departure_at uses the
    scan day at local midnight — the heartbeat engine only needs a stable
    datetime, not a precise gate time.
    """
    from agents.oakstreet import AlertEvent  # local import on purpose
    depart = datetime.combine(_scan_day(config), time(hour=0, minute=0))
    return AlertEvent(
        deal_id=make_deal_key(result),
        color=result.color.value.lower(),
        price_usd=float(result.classification.price_usd),
        route_signature=_route_signature(result) or "",
        departure_at=depart,
        observed_at=datetime.now(),
        summary=result.classification.explanation,
    )


async def _emit_red(context, result, key: str) -> None:
    """Emit a RED deal.

    Layer 7B: when the Oak Street pipeline is wired into bot_data AND the
    scanner kill switch is off, route through the full
    ingest_alert -> specialists -> dispatch_briefing flow. Otherwise fall
    back to the legacy single-alert send. DRY_RUN-safe either way — the
    pipeline only touches the dispatcher, which is hermetic under DRY_RUN.
    """
    data = context.bot_data
    pipeline = data.get("desk_pipeline")
    desk_config = data.get("desk_config")
    if (pipeline is not None and desk_config is not None
            and not desk_config.scanner_telegram_enabled):
        pipeline.process_event(_event_from_result(result, data["config"]))
        return
    await _send(
        context, format_deal_alert(result),
        kind="alert", color="red", deal_id=key,
        route_signature=_route_signature(result),
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
                await _emit_red(context, result, key)
                storage.mark_alerted(key)
        elif color == DealColor.YELLOW:
            yellows += 1
            if not storage.was_alerted(key):
                await _send(
                    context, format_deal_alert(result),
                    kind="alert", color="yellow", deal_id=key,
                    route_signature=_route_signature(result),
                )
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
        await _send(context, text, kind="heartbeat", color="red")

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
    await _send(context, format_daily_summary(results, scan_time), kind="digest")


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
