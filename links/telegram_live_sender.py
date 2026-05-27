"""Live Telegram sender — wraps python-telegram-bot's `telegram.Bot`
into the simple `sender(chat_id, text) -> message_id` callable that
`links.telegram_dispatcher.TelegramDispatcher` expects.

This is the only place in the new code that performs an actual network
call to Telegram. It is intentionally tiny and synchronous-from-callers'
perspective: it runs the async send inside its own event loop. That
keeps the dispatcher's surface uniform for synchronous and asynchronous
call sites alike.

When you need to push from inside an already-running asyncio loop
(e.g. python-telegram-bot's JobQueue handlers), prefer using
`telegram.Bot.send_message(...)` directly; the dispatcher accepts any
callable, so a context-bound async helper works too.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from agents.logging_setup import get_logger

log = get_logger("live_sender")


class LiveTelegramSender:
    """Tiny `telegram.Bot.send_message` adapter.

    Construct once and pass `.send` (bound method) to the dispatcher's
    `sender` attribute. The instance owns its own event loop so calls
    from synchronous contexts work.
    """

    def __init__(self, bot_token: str, parse_mode: str = "HTML"):
        # Imported lazily so test environments without python-telegram-bot
        # can still import this module (the constructor will fail, but
        # the package import does not).
        from telegram import Bot

        self._bot = Bot(token=bot_token)
        self._parse_mode = parse_mode
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_message_id: Optional[int] = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def send(self, chat_id: str, text: str) -> None:
        """Synchronous send. Returns None; the dispatcher cares about
        success/failure, not the message id. We stash the last id on
        `self._last_message_id` for the audit log to read."""
        loop = self._ensure_loop()
        coro = self._bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=self._parse_mode,
            disable_web_page_preview=True,
        )
        message = loop.run_until_complete(coro)
        self._last_message_id = getattr(message, "message_id", None)
        log.info("live send -> chat=%s msg_id=%s len=%d",
                 chat_id, self._last_message_id, len(text))

    @property
    def last_message_id(self) -> Optional[int]:
        return self._last_message_id
