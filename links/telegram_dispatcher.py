"""Telegram dispatcher — the only path the Colombia Desk uses to talk to
Telegram.

Honors DRY_RUN: when enabled, no network calls. Every send is recorded
on the dispatcher's `outbox` for inspection by simulations and tests.
This is the abstraction layer that lets Oak Street render in "one voice"
without each agent owning its own Telegram client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

from agents.logging_setup import get_logger

log = get_logger("telegram")


@dataclass
class DispatchedMessage:
    sent_at: datetime
    chat_id: str
    text: str
    kind: str            # "alert" | "heartbeat" | "digest" | "system"
    deal_id: Optional[str]
    dry_run: bool


@dataclass
class TelegramDispatcher:
    """One-voice Telegram dispatcher.

    `sender` is an optional callable: `sender(chat_id, text) -> None`.
    When None (or when dry_run is True), messages are recorded in the
    outbox only — no network call is made. This keeps Layer 1 fully
    hermetic until you wire a live Telegram client.
    """
    bot_token: str
    chat_id: str
    dry_run: bool = False
    sender: Optional[Callable[[str, str], None]] = None
    outbox: List[DispatchedMessage] = field(default_factory=list)

    def send(
        self,
        text: str,
        *,
        kind: str = "system",
        deal_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> DispatchedMessage:
        when = now or datetime.now()
        message = DispatchedMessage(
            sent_at=when,
            chat_id=self.chat_id,
            text=text,
            kind=kind,
            deal_id=deal_id,
            dry_run=self.dry_run,
        )
        self.outbox.append(message)
        if self.dry_run:
            log.info("DRY_RUN suppress %s deal=%s len=%d", kind, deal_id, len(text))
            return message
        if self.sender is None:
            log.info("No sender wired; recorded only (kind=%s deal=%s)", kind, deal_id)
            return message
        try:
            self.sender(self.chat_id, text)
            log.info("Sent %s deal=%s", kind, deal_id)
        except Exception:
            log.exception("Telegram send failed (kind=%s deal=%s)", kind, deal_id)
        return message

    def clear(self) -> None:
        self.outbox.clear()
