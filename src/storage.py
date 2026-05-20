"""JSON-backed persistence: alert dedupe, scan history, deal logs.

Deduplication is content-based: every deal gets a stable SHA-1 key built
from its destination, routing, rounded price, and departure date, so the
same offer is never alerted twice — even across restarts. Region-neutral.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

ALERT_DEDUPE_HOURS = 12


def make_deal_key(result) -> str:
    """Stable content hash for a deal (destination + routing + price + date)."""
    comp = result.comparison
    rec = comp.recommended
    if rec is None:
        raw = f"{comp.destination}|none"
    else:
        raw = "|".join(
            [
                comp.destination,
                rec.strategy,
                rec.gateway or "-",
                str(int(round(rec.total_price))),
                rec.depart_dt.strftime("%Y-%m-%d"),
            ]
        )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _safe_dt(value):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _result_row(result) -> dict:
    comp = result.comparison
    cls = result.classification
    rec = comp.recommended
    return {
        "destination": comp.destination,
        "color": cls.color.value,
        "price_usd": rec.total_price if rec else None,
        "strategy": rec.strategy if rec else None,
        "gateway": rec.gateway if rec else None,
        "effective_savings_usd": cls.effective_savings_usd,
        "urgency_score": cls.urgency_score,
        "deal_key": make_deal_key(result),
    }


class Storage:
    """Thread-safe JSON storage rooted at a log directory."""

    def __init__(self, log_dir: str | Path = "logs"):
        self.dir = Path(log_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.alerts_file = self.dir / "alerted_deals.json"
        self.history_file = self.dir / "scan_history.json"
        self.deal_log = self.dir / "deal_log.jsonl"
        self.red_file = self.dir / "active_red_deals.json"

    def _read(self, path: Path, default):
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write(self, path: Path, data) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        tmp.replace(path)

    def was_alerted(self, deal_key: str) -> bool:
        with self._lock:
            alerts = self._read(self.alerts_file, {})
        when = _safe_dt(alerts.get(deal_key))
        if when is None:
            return False
        return datetime.now() - when < timedelta(hours=ALERT_DEDUPE_HOURS)

    def mark_alerted(self, deal_key: str) -> None:
        with self._lock:
            alerts = self._read(self.alerts_file, {})
            now = datetime.now()
            alerts[deal_key] = now.isoformat()
            cutoff = now - timedelta(hours=ALERT_DEDUPE_HOURS * 2)
            alerts = {
                k: v
                for k, v in alerts.items()
                if (_safe_dt(v) is not None and _safe_dt(v) > cutoff)
            }
            self._write(self.alerts_file, alerts)

    def record_scan(self, results, scan_time: datetime) -> None:
        rows = [_result_row(r) for r in results]
        with self._lock:
            history = self._read(self.history_file, [])
            history.append({"scan_time": scan_time.isoformat(), "deals": rows})
            history = history[-200:]
            self._write(self.history_file, history)
            with self.deal_log.open("a", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(
                        json.dumps({"scan_time": scan_time.isoformat(), **row}) + "\n"
                    )

    def scan_count(self) -> int:
        with self._lock:
            return len(self._read(self.history_file, []))

    def save_active_red(self, entries: dict) -> None:
        with self._lock:
            self._write(self.red_file, entries)

    def load_active_red(self) -> dict:
        with self._lock:
            return self._read(self.red_file, {})
