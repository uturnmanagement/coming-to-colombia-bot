"""Telegram dispatcher — the only path the Colombia Desk uses to talk to
Telegram.

Layer 1 introduced the dispatcher as an abstraction with an outbox.
Layer 2 hardens it for live operation:

    - **Severity gate.** Only RED initial alerts and qualifying
      heartbeats reach the wire. YELLOW/GREEN initial alerts and
      digests stay recorded-but-unsent. System messages pass.
    - **Dedupe.** A short rolling window suppresses repeated identical
      payloads — the same (deal_id, kind, text_hash) cannot fire twice
      back-to-back.
    - **Per-deal cooldown.** A floor (default 60 s) between any two
      live sends for the same deal_id, regardless of trigger. The
      heartbeat decay engine is the *intelligent* rate limiter; this
      cooldown is the *safety* rate limiter — belt and suspenders.
    - **Audit.** Every decision (sent / dry-run / suppressed / errored)
      is written as one JSONL line to logs/colombia_desk_live_sends.jsonl
      via `LiveSendAuditor`.

`DRY_RUN` short-circuits the wire path entirely: outbox records the
message, audit logs the dry_run outcome, sender callable is never
invoked.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from agents.logging_setup import get_logger
from links.live_send_audit import LiveSendAuditor

log = get_logger("telegram")


# Allow-list applied to live sends (DRY_RUN bypasses this entirely so
# simulations can exercise every render path).
_LIVE_PASS_KINDS_ANY_COLOR = {"heartbeat", "system"}
_LIVE_PASS_KINDS_RED_ONLY = {"alert"}
_LIVE_BLOCKED_KINDS = {"digest"}


@dataclass
class DispatchedMessage:
    sent_at: datetime
    chat_id: str
    text: str
    kind: str
    deal_id: Optional[str]
    color: Optional[str]
    route_signature: Optional[str]
    dry_run: bool
    outcome: str               # see LiveSendAuditor.outcome values
    reason: str


@dataclass
class TelegramDispatcher:
    """Centralized Telegram dispatcher.

    Attach an auditor with `attach_auditor(...)`; without one, audit
    logging is silently skipped (useful in unit tests that don't care).
    """
    bot_token: str
    chat_id: str
    dry_run: bool = False
    sender: Optional[Callable[[str, str], None]] = None
    cooldown_seconds: int = 60
    dedupe_window_seconds: int = 300

    outbox: List[DispatchedMessage] = field(default_factory=list)
    auditor: Optional[LiveSendAuditor] = None
    _last_send_at: Dict[str, datetime] = field(default_factory=dict)
    _recent_payloads: Dict[str, datetime] = field(default_factory=dict)

    # --- configuration ---------------------------------------------------

    def attach_auditor(self, auditor: LiveSendAuditor) -> None:
        self.auditor = auditor

    # --- core --------------------------------------------------------------

    def send(
        self,
        text: str,
        *,
        kind: str = "system",
        deal_id: Optional[str] = None,
        color: Optional[str] = None,
        route_signature: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> DispatchedMessage:
        when = now or datetime.now()

        # 1. DRY_RUN bypasses every wire path but still records + audits.
        if self.dry_run:
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="dry_run", reason="DRY_RUN suppress",
                message_id=None,
            )

        # 2. Severity gate (live rules).
        passes, gate_reason = self._passes_live_gate(kind, color)
        if not passes:
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="suppressed_gate", reason=gate_reason,
                message_id=None,
            )

        # 3. Dedupe (no duplicate route signatures / identical payloads).
        dedupe_key = self._dedupe_key(deal_id, kind, text)
        if self._is_recent_duplicate(dedupe_key, when):
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="suppressed_dedupe",
                reason=f"identical payload in last {self.dedupe_window_seconds}s",
                message_id=None,
            )

        # 4. Per-deal cooldown (safety floor).
        if deal_id and self._in_cooldown(deal_id, when):
            cooldown_remaining = self._cooldown_remaining(deal_id, when)
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="suppressed_cooldown",
                reason=(
                    f"per-deal cooldown {self.cooldown_seconds}s; "
                    f"{cooldown_remaining}s remaining"
                ),
                message_id=None,
            )

        # 5. Live send.
        if self.sender is None:
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="no_sender",
                reason="no live sender wired",
                message_id=None,
            )

        try:
            self.sender(self.chat_id, text)
        except Exception as exc:  # noqa: BLE001 — explicit audit path
            log.exception("Telegram send failed kind=%s deal=%s", kind, deal_id)
            return self._record(
                text=text, kind=kind, deal_id=deal_id, color=color,
                route_signature=route_signature, when=when,
                outcome="send_error",
                reason=f"{type(exc).__name__}: {exc}",
                message_id=None,
            )

        raw_id = getattr(self.sender, "last_message_id", None)
        message_id = raw_id if isinstance(raw_id, int) else None
        if deal_id:
            self._last_send_at[deal_id] = when
        self._recent_payloads[dedupe_key] = when
        return self._record(
            text=text, kind=kind, deal_id=deal_id, color=color,
            route_signature=route_signature, when=when,
            outcome="sent", reason="live send ok",
            message_id=message_id,
        )

    def clear(self) -> None:
        self.outbox.clear()
        self._last_send_at.clear()
        self._recent_payloads.clear()

    # --- internals -------------------------------------------------------

    def _record(
        self,
        *,
        text: str,
        kind: str,
        deal_id: Optional[str],
        color: Optional[str],
        route_signature: Optional[str],
        when: datetime,
        outcome: str,
        reason: str,
        message_id: Optional[int],
    ) -> DispatchedMessage:
        message = DispatchedMessage(
            sent_at=when,
            chat_id=self.chat_id,
            text=text,
            kind=kind,
            deal_id=deal_id,
            color=color,
            route_signature=route_signature,
            dry_run=self.dry_run,
            outcome=outcome,
            reason=reason,
        )
        self.outbox.append(message)
        if self.auditor is not None:
            self.auditor.record(
                text=text, kind=kind, outcome=outcome, reason=reason,
                dry_run=self.dry_run, deal_id=deal_id, color=color,
                route_signature=route_signature, message_id=message_id,
                now=when,
            )
        log.info(
            "dispatch outcome=%s kind=%s deal=%s color=%s reason=%s",
            outcome, kind, deal_id, color, reason,
        )
        return message

    def _passes_live_gate(
        self, kind: str, color: Optional[str]
    ) -> tuple[bool, str]:
        """Layer 2 live rules: only RED alerts + heartbeats + system."""
        if kind in _LIVE_PASS_KINDS_ANY_COLOR:
            return True, "kind always allowed"
        if kind in _LIVE_BLOCKED_KINDS:
            return False, f"kind '{kind}' blocked from live"
        if kind in _LIVE_PASS_KINDS_RED_ONLY:
            normalized = (color or "").lower()
            if normalized == "red":
                return True, "RED alert"
            return False, (
                f"alert color '{color}' below RED threshold; "
                "live path is RED-only for initial alerts"
            )
        return False, f"unknown kind '{kind}'"

    def _dedupe_key(self, deal_id: Optional[str], kind: str, text: str) -> str:
        digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"{deal_id or '-'}::{kind}::{digest}"

    def _is_recent_duplicate(self, dedupe_key: str, now: datetime) -> bool:
        last = self._recent_payloads.get(dedupe_key)
        if last is None:
            return False
        return (now - last) < timedelta(seconds=self.dedupe_window_seconds)

    def _in_cooldown(self, deal_id: str, now: datetime) -> bool:
        last = self._last_send_at.get(deal_id)
        if last is None:
            return False
        return (now - last) < timedelta(seconds=self.cooldown_seconds)

    def _cooldown_remaining(self, deal_id: str, now: datetime) -> int:
        last = self._last_send_at[deal_id]
        elapsed = (now - last).total_seconds()
        return max(0, int(self.cooldown_seconds - elapsed))
