"""Oak Street — master orchestrator skeleton.

Boundary rules (enforced by code structure, not just convention):
    - No external API calls live in this module. Everything outbound
      goes through `links.telegram_dispatcher.TelegramDispatcher`.
    - All Telegram output is rendered here. Specialists (future layers)
      submit structured reports; Oak Street decides the final wording
      and ordering — "one voice".
    - State lives in `db.sqlite_manager.SqliteManager`. Oak Street does
      not own its own persistence.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agents.logging_setup import get_logger
from db.sqlite_manager import SqliteManager
from intel.heartbeat import (
    AlertSnapshot,
    HeartbeatDecision,
    HeartbeatStage,
    decide_heartbeat,
)
from links.telegram_dispatcher import TelegramDispatcher

log = get_logger("oakstreet")


@dataclass(frozen=True)
class AlertEvent:
    """An observation from the scanner.

    The scanner already classifies into GREEN/YELLOW/RED. Oak Street
    consumes the observation; it does not redo the classification.
    """
    deal_id: str
    color: str               # "green" | "yellow" | "red"
    price_usd: float
    route_signature: str
    departure_at: datetime
    observed_at: datetime
    summary: str             # short human-readable from the scanner
    is_first_observation: bool = False


@dataclass
class OakStreet:
    """Master orchestrator skeleton."""
    db: SqliteManager
    dispatcher: TelegramDispatcher
    # In-memory cache of previous snapshots, keyed by deal_id. Persistence
    # of these lives in the deals table; this cache is for hot lookups
    # within a process lifetime.
    _last_snapshot: dict[str, AlertSnapshot] = field(default_factory=dict)

    # --- ingress ---------------------------------------------------------

    def ingest_alert(self, event: AlertEvent) -> Optional[HeartbeatDecision]:
        """Route an alert through the heartbeat engine and dispatcher.

        Returns the HeartbeatDecision for inspection / tests / sims.
        Returns None for the *first* observation of a deal, which always
        emits as a normal alert (not a heartbeat).
        """
        log.debug("Ingest deal=%s color=%s price=%.0f",
                  event.deal_id, event.color, event.price_usd)

        current = AlertSnapshot(
            deal_id=event.deal_id,
            color=event.color,
            price_usd=event.price_usd,
            route_signature=event.route_signature,
            departure_at=event.departure_at,
        )

        deal_row = self.db.get_deal(event.deal_id)
        if deal_row is None:
            # First observation — register and emit initial alert.
            self.db.upsert_deal(
                deal_id=event.deal_id,
                first_alert_at=event.observed_at,
                color=event.color,
                price_usd=event.price_usd,
                route_signature=event.route_signature,
                departure_at=event.departure_at,
                now=event.observed_at,
            )
            self._last_snapshot[event.deal_id] = current
            text = self._render_initial(event)
            self.dispatcher.send(
                text, kind="alert", deal_id=event.deal_id, now=event.observed_at
            )
            return None

        first_alert_at = datetime.fromisoformat(deal_row["first_alert_at"])
        last_heartbeat_at = (
            datetime.fromisoformat(deal_row["last_heartbeat_at"])
            if deal_row.get("last_heartbeat_at") else None
        )
        previous = self._last_snapshot.get(event.deal_id) or _snapshot_from_row(deal_row)

        decision = decide_heartbeat(
            previous=previous,
            current=current,
            first_alert_at=first_alert_at,
            last_heartbeat_at=last_heartbeat_at,
            now=event.observed_at,
        )

        if decision.stage is HeartbeatStage.ZOMBIE:
            self.db.mark_stage(event.deal_id, HeartbeatStage.ZOMBIE.value, event.observed_at)

        if decision.should_emit:
            text = self._render_heartbeat(event, decision)
            self.dispatcher.send(
                text,
                kind="heartbeat",
                deal_id=event.deal_id,
                now=event.observed_at,
            )
            self.db.update_after_heartbeat(
                deal_id=event.deal_id,
                heartbeat_at=event.observed_at,
                stage=decision.stage.value,
                color=event.color,
                price_usd=event.price_usd,
                route_signature=event.route_signature,
                departure_at=event.departure_at,
            )
            self.db.insert_snapshot(
                deal_id=event.deal_id,
                emitted_at=event.observed_at,
                stage=decision.stage.value,
                color=event.color,
                price_usd=event.price_usd,
                route_signature=event.route_signature,
                departure_at=event.departure_at,
                trigger_reason=decision.reason,
            )
            self._last_snapshot[event.deal_id] = current
        else:
            log.info(
                "Heartbeat suppressed deal=%s stage=%s reason=%s",
                event.deal_id, decision.stage.value, decision.reason,
            )
        return decision

    # --- specialist reports (placeholder for Layer 2+) -------------------

    def ingest_specialist_report(
        self,
        specialist: str,
        payload: dict,
        *,
        deal_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Stub that records a specialist report.

        Layer 2 (Echo/India/Juliet) will rewire the renderers above to
        consume these reports and inject them into Oak Street's output.
        """
        when = now or datetime.now()
        self.db.insert_specialist_report(
            specialist=specialist,
            report_at=when,
            payload_json=json.dumps(payload, default=str),
            deal_id=deal_id,
        )
        log.info("Recorded specialist report from %s (deal=%s)", specialist, deal_id)

    # --- rendering (one-voice) -------------------------------------------

    def _render_initial(self, event: AlertEvent) -> str:
        icon = _color_icon(event.color)
        return (
            f"{icon} <b>Colombia Desk — {event.color.upper()} deal</b>\n"
            f"{event.summary}\n"
            f"Route: {event.route_signature}\n"
            f"Price: ${event.price_usd:.0f}\n"
            f"Depart: {event.departure_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"Deal id: <code>{event.deal_id}</code>"
        )

    def _render_heartbeat(
        self, event: AlertEvent, decision: HeartbeatDecision
    ) -> str:
        icon = _color_icon(event.color)
        return (
            f"{icon} <b>Colombia Desk — heartbeat ({decision.stage.value})</b>\n"
            f"{event.summary}\n"
            f"Route: {event.route_signature}\n"
            f"Price: ${event.price_usd:.0f}\n"
            f"Trigger: {decision.reason}\n"
            f"Deal age: {decision.age_hours:.1f}h\n"
            f"Deal id: <code>{event.deal_id}</code>"
        )


def _snapshot_from_row(row: dict) -> Optional[AlertSnapshot]:
    if row.get("last_price_usd") is None or not row.get("last_departure_at"):
        return None
    return AlertSnapshot(
        deal_id=row["deal_id"],
        color=row.get("last_color") or "",
        price_usd=float(row["last_price_usd"]),
        route_signature=row.get("last_route_signature") or "",
        departure_at=datetime.fromisoformat(row["last_departure_at"]),
    )


def _color_icon(color: str) -> str:
    return {"red": "🔴", "yellow": "🟡", "green": "🟢"}.get(color.lower(), "⚪")
