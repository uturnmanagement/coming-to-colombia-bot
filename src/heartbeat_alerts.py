"""RED-deal heartbeat manager.

When a RED deal appears, the radar pings every RED_HEARTBEAT_MINUTES for
RED_HEARTBEAT_DURATION_HOURS, then stops — unless the deal is still live
and still RED. Tracked per destination so the same deal never spams.

Region-neutral: it re-checks deals through route_compare/deal_classifier
and emits text through a caller-supplied async `send` callable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from . import region
from .alert_formatter import format_heartbeat_alert, format_heartbeat_end
from .deal_classifier import DealColor, classify_route
from .route_compare import compare_routes

# Hard safety cap: a deal that stays RED forever still stops pinging here.
SAFETY_CAP_HOURS = 24


@dataclass
class HeartbeatEntry:
    destination: str
    started_at: datetime
    last_pulse_at: datetime
    pulses: int = 0


class HeartbeatManager:
    def __init__(self, config, fetcher, storage=None):
        self.config = config
        self.fetcher = fetcher
        self.storage = storage
        self.active: dict[str, HeartbeatEntry] = {}

    @property
    def duration(self) -> timedelta:
        return timedelta(hours=self.config.red_heartbeat_duration_hours)

    def active_count(self) -> int:
        return len(self.active)

    def active_destinations(self) -> list[str]:
        return list(self.active)

    def register(self, destination: str, now: datetime | None = None) -> bool:
        """Start tracking a RED destination. Returns True if newly added."""
        now = now or datetime.now()
        if destination in self.active:
            return False
        self.active[destination] = HeartbeatEntry(
            destination=destination, started_at=now, last_pulse_at=now
        )
        self._persist()
        return True

    def _remove(self, destination: str) -> None:
        self.active.pop(destination, None)
        self._persist()

    def _persist(self) -> None:
        if self.storage is None:
            return
        self.storage.save_active_red(
            {
                d: {
                    "started_at": e.started_at.isoformat(),
                    "last_pulse_at": e.last_pulse_at.isoformat(),
                    "pulses": e.pulses,
                }
                for d, e in self.active.items()
            }
        )

    def _scan_day(self) -> date:
        return datetime.now().date() + timedelta(days=self.config.scan_days_ahead)

    async def tick(self, send) -> None:
        """Run one heartbeat cycle. `send` is an async callable(text)."""
        now = datetime.now()
        for destination in list(self.active):
            entry = self.active[destination]
            elapsed = now - entry.started_at

            comparison = compare_routes(
                self.fetcher, destination, self.config, self._scan_day()
            )
            result = classify_route(comparison, self.config)
            still_red = result.color == DealColor.RED

            if not still_red:
                await send(
                    format_heartbeat_end(
                        destination,
                        f"{region.city_label(destination)} cooled off — now "
                        f"{result.color.value}. Heartbeat stopped.",
                    )
                )
                self._remove(destination)
                continue

            if elapsed >= timedelta(hours=SAFETY_CAP_HOURS):
                await send(
                    format_heartbeat_end(
                        destination,
                        f"{region.city_label(destination)} still RED after "
                        f"{SAFETY_CAP_HOURS}h — heartbeat auto-stopped.",
                    )
                )
                self._remove(destination)
                continue

            entry.pulses += 1
            entry.last_pulse_at = now
            elapsed_minutes = elapsed.total_seconds() / 60.0
            past_window = elapsed >= self.duration
            await send(
                format_heartbeat_alert(
                    result, entry.pulses, elapsed_minutes, past_window
                )
            )
            self._persist()
