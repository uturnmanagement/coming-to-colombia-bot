"""Telegram command handlers.

The fixed commands (/start, /deals, /red, ...) are static; the
per-destination commands (/bogota, /tokyo, ...) are generated at startup
from the active region pack, so cloning the bot to a new market needs no
handler code changes.
"""
from __future__ import annotations

import logging
import unicodedata

from telegram.constants import ParseMode
from telegram.ext import CommandHandler

from . import region
from .alert_formatter import (
    format_deals_list,
    format_destination_detail,
    format_positioning_report,
    format_status,
)
from .deal_classifier import DealColor

log = logging.getLogger("airfare.handlers")


def command_slug(text: str) -> str:
    """Turn a city name into a Telegram-safe command (Bogotá -> bogota)."""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in ascii_only.lower() if ch.isalnum())


def destination_commands() -> dict[str, str]:
    """Map command name -> destination code from the active region pack."""
    pack = region.active()
    commands: dict[str, str] = {}
    for code, dest in pack.destinations.items():
        slug = command_slug(dest.city) or code.lower()
        commands.setdefault(slug, code)
        commands.setdefault(code.lower(), code)  # the IATA code also works
    return commands


def _start_text() -> str:
    pack = region.active()
    return (
        f"<b>✈️ {esc(pack.name)} Airfare Intelligence</b>\n\n"
        f"I track cheap one-way flights from <b>{esc(pack.origin_label)}</b> "
        f"to {esc(pack.name)} and compare two strategies:\n\n"
        "<b>A. Direct:</b> origin → destination\n"
        "<b>B. Positioning:</b> origin → gateway → destination\n\n"
        "Deals are graded:\n"
        "🟢 <b>GREEN</b> — normal, in the daily digest\n"
        "🟡 <b>YELLOW</b> — strong deal, you get an alert\n"
        "🔴 <b>RED</b> — rare urgent deal, alert + heartbeats\n\n"
        "Send /help for the full command list."
    )


def _help_text() -> str:
    pack = region.active()
    cmds = sorted(
        {command_slug(d.city) or c.lower() for c, d in pack.destinations.items()}
    )
    city_cmds = "  ".join(f"/{c}" for c in cmds)
    return (
        "<b>📋 Commands</b>\n\n"
        "/deals — all destinations, latest scan\n"
        "/red — RED deals only\n"
        "/yellow — YELLOW deals only\n"
        "/green — GREEN deals only\n"
        "/positioning — direct vs positioning comparison\n\n"
        "<b>By destination:</b>\n"
        f"{city_cmds}\n\n"
        "<b>Utility:</b>\n"
        "/status — radar status &amp; cadence\n"
        "/chatid — show this chat's ID for .env\n"
        "/start — overview · /help — this message"
    )


def esc(text) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _results(context) -> list:
    return context.bot_data.get("latest_results") or []


async def _reply(update, text: str) -> None:
    await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


async def cmd_start(update, context) -> None:
    await _reply(update, _start_text())


async def cmd_help(update, context) -> None:
    await _reply(update, _help_text())


async def cmd_chatid(update, context) -> None:
    chat = update.effective_chat
    await _reply(
        update,
        f"<b>Chat ID:</b> <code>{chat.id}</code>\n\n"
        "Copy this into <code>TELEGRAM_CHAT_ID</code> in your .env file, "
        "then restart the bot so alerts land here.",
    )


async def cmd_status(update, context) -> None:
    data = context.bot_data
    await _reply(
        update,
        format_status(
            data["config"],
            data.get("last_scan_at"),
            _results(context),
            data["heartbeat"].active_count(),
        ),
    )


async def cmd_deals(update, context) -> None:
    await _reply(
        update,
        format_deals_list(_results(context), title="Latest deals — all colors"),
    )


async def cmd_red(update, context) -> None:
    await _reply(
        update,
        format_deals_list(_results(context), DealColor.RED, title="🔴 RED deals"),
    )


async def cmd_yellow(update, context) -> None:
    await _reply(
        update,
        format_deals_list(
            _results(context), DealColor.YELLOW, title="🟡 YELLOW deals"
        ),
    )


async def cmd_green(update, context) -> None:
    await _reply(
        update,
        format_deals_list(_results(context), DealColor.GREEN, title="🟢 GREEN deals"),
    )


async def cmd_positioning(update, context) -> None:
    await _reply(update, format_positioning_report(_results(context)))


def _make_destination_handler(dest_code: str):
    async def handler(update, context) -> None:
        match = next(
            (r for r in _results(context) if r.destination == dest_code), None
        )
        if match is None:
            await _reply(
                update,
                f"No data yet for {region.city_label(dest_code)}. "
                "The first scan runs at startup — try /deals in a minute.",
            )
        else:
            await _reply(update, format_destination_detail(match))

    return handler


def register_handlers(application) -> None:
    """Attach static + region-generated command handlers."""
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("chatid", cmd_chatid))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("deals", cmd_deals))
    application.add_handler(CommandHandler("red", cmd_red))
    application.add_handler(CommandHandler("yellow", cmd_yellow))
    application.add_handler(CommandHandler("green", cmd_green))
    application.add_handler(CommandHandler("positioning", cmd_positioning))

    dest_commands = destination_commands()
    for command, dest in dest_commands.items():
        application.add_handler(
            CommandHandler(command, _make_destination_handler(dest))
        )
    log.info(
        "registered %d static + %d destination command handlers",
        9, len(dest_commands),
    )
