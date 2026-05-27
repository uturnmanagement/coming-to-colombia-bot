"""Rollback-safe audit logger for every Telegram send attempt.

Writes append-only JSONL records to `logs/colombia_desk_live_sends.jsonl`
(path configurable via LIVE_SEND_AUDIT_LOG). Every dispatcher.send() —
sent, suppressed, deduped, or dry-run — gets one line. The file is
designed for post-mortem and rollback: each record carries enough
information to reproduce the suppression / send decision after the fact.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.logging_setup import get_logger

log = get_logger("audit")


@dataclass(frozen=True)
class AuditRecord:
    timestamp: str
    deal_id: Optional[str]
    kind: str                  # "alert" | "heartbeat" | "digest" | "system"
    color: Optional[str]
    route_signature: Optional[str]
    outcome: str               # "sent" | "dry_run" | "suppressed_gate"
                               # | "suppressed_dedupe" | "suppressed_cooldown"
                               # | "no_sender" | "send_error"
    reason: str
    text_hash: str             # sha1[:16] of the rendered message
    text_length: int
    message_id: Optional[int]  # Telegram message id when sent live
    dry_run: bool


class LiveSendAuditor:
    """Append-only JSONL writer for live-send decisions.

    Thread-safe (a process-internal lock guards file appends). Crash-safe
    in the sense that each record is one line — a partial write of one
    line at most is lost.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()
        # Ensure parent dir exists; the file itself is created on first write.
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        text: str,
        kind: str,
        outcome: str,
        reason: str,
        dry_run: bool,
        deal_id: Optional[str] = None,
        color: Optional[str] = None,
        route_signature: Optional[str] = None,
        message_id: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> AuditRecord:
        when = now or datetime.now()
        digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        record = AuditRecord(
            timestamp=when.isoformat(),
            deal_id=deal_id,
            kind=kind,
            color=color,
            route_signature=route_signature,
            outcome=outcome,
            reason=reason,
            text_hash=digest,
            text_length=len(text),
            message_id=message_id,
            dry_run=dry_run,
        )
        line = json.dumps(asdict(record), separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        log.debug("audit %s deal=%s kind=%s outcome=%s reason=%s",
                  digest, deal_id, kind, outcome, reason)
        return record
