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
    # Per-deal specialist-report cache: deal_id -> {agent -> SpecialistReport}.
    # Populated by `ingest_report`, consumed by `synthesize_briefing`.
    _reports_cache: dict[str, dict[str, object]] = field(default_factory=dict)

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
                text,
                kind="alert",
                deal_id=event.deal_id,
                color=event.color,
                route_signature=event.route_signature,
                now=event.observed_at,
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
                color=event.color,
                route_signature=event.route_signature,
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

    # --- specialist reports ----------------------------------------------

    def ingest_specialist_report(
        self,
        specialist: str,
        payload: dict,
        *,
        deal_id: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Untyped legacy ingestion path — retained for Layer 1 callers.

        New Layer 3 specialists hand in a `SpecialistReport` via
        `ingest_report(...)` below. This older method still works for
        ad-hoc payloads and is what the `specialist_reports` table
        was originally wired against.
        """
        when = now or datetime.now()
        self.db.insert_specialist_report(
            specialist=specialist,
            report_at=when,
            payload_json=json.dumps(payload, default=str),
            deal_id=deal_id,
        )
        log.info("Recorded specialist report from %s (deal=%s)", specialist, deal_id)

    def ingest_report(self, report) -> None:
        """Typed ingestion path used by Delta / Echo / future specialists.

        Persists the report under the agent name and caches it per-deal
        so `synthesize_briefing(deal_id)` can pull every specialist's
        contribution together. No Telegram side-effects from this call;
        the briefing is produced explicitly via `synthesize_briefing`.
        """
        # Late-bound import to avoid a circular dependency at module
        # load time (the specialists import this module).
        from agents.specialist_report import SpecialistReport

        if not isinstance(report, SpecialistReport):
            raise TypeError(
                f"ingest_report expects a SpecialistReport, got {type(report).__name__}"
            )
        self.db.insert_specialist_report(
            specialist=report.agent,
            report_at=report.observed_at,
            payload_json=report.to_json(),
            deal_id=report.deal_id,
        )
        if report.deal_id is not None:
            self._reports_cache.setdefault(report.deal_id, {})[report.agent] = report
        log.info(
            "Recorded SpecialistReport agent=%s status=%s conf=%.2f deal=%s",
            report.agent, report.status.value, report.confidence, report.deal_id,
        )

    def synthesize_briefing(
        self, deal_id: str, *, now: Optional[datetime] = None
    ) -> Optional[str]:
        """Combine the cached specialist reports for one deal into a
        single internal briefing text. DRY_RUN-safe: this only renders
        text; whether to send is the dispatcher's call.

        Returns None when no reports are cached yet for the deal.
        """
        when = now or datetime.now()
        reports = self._reports_cache.get(deal_id)
        if not reports:
            return None

        deal_row = self.db.get_deal(deal_id)
        header = self._render_briefing_header(deal_id, deal_row)
        sections: list[str] = [header]

        delta = reports.get("delta")
        if delta is not None:
            sections.append(self._render_delta_section(delta))
        echo = reports.get("echo")
        if echo is not None:
            sections.append(self._render_echo_section(echo))
        india = reports.get("india")
        if india is not None:
            sections.append(self._render_india_section(india))

        # Unknown specialists (future Juliet / etc.) appear after the
        # named ones, in deterministic order.
        for name in sorted(reports):
            if name in ("delta", "echo", "india"):
                continue
            sections.append(
                f"<b>{name.upper()}</b> — status={reports[name].status.value} "
                f"conf={reports[name].confidence:.2f}"
            )

        footer = (
            f"\n<i>Internal briefing rendered at "
            f"{when.strftime('%Y-%m-%d %H:%M:%S')} — DRY_RUN check at dispatch.</i>"
        )
        return "\n\n".join(sections) + footer

    def dispatch_briefing(
        self, deal_id: str, *, color: str = "red",
        route_signature: str = "", now: Optional[datetime] = None,
    ) -> Optional[str]:
        """Render the briefing and push through the centralized
        dispatcher with kind='heartbeat'. Layer 3 keeps DRY_RUN=true,
        so the dispatcher will record-and-not-send; the rendered text
        is still returned for inspection.
        """
        text = self.synthesize_briefing(deal_id, now=now)
        if text is None:
            return None
        self.dispatcher.send(
            text,
            kind="heartbeat",   # heartbeat-channel is the natural carrier
            deal_id=deal_id,
            color=color,
            route_signature=route_signature,
            now=now,
        )
        return text

    # --- briefing rendering ----------------------------------------------

    def _render_briefing_header(self, deal_id: str, deal_row) -> str:
        if not deal_row:
            return (
                f"🧭 <b>Colombia Desk — internal briefing</b>\n"
                f"Deal id: <code>{deal_id}</code>"
            )
        color_raw = deal_row.get("last_color") or ""
        color_label = color_raw.upper() if color_raw else "?"
        icon = _color_icon(color_raw)
        price = deal_row.get("last_price_usd")
        route = deal_row.get("last_route_signature") or "?"
        lines = [
            f"{icon} <b>Colombia Desk — internal briefing ({color_label})</b>",
            f"Route: {route}",
        ]
        if isinstance(price, (int, float)):
            lines.append(f"Outbound price: ${price:.0f}")
        lines.append(f"Deal id: <code>{deal_id}</code>")
        return "\n".join(lines)

    def _render_delta_section(self, report) -> str:
        lines = [f"<b>DELTA · return pairing</b> ({report.status.value}, conf {report.confidence:.2f})"]
        options = report.payload.get("options", [])
        priced = [o for o in options if o.get("round_trip_total_usd") is not None]
        if not priced:
            lines.append("  no priced return windows")
        else:
            best = min(priced, key=lambda o: o["round_trip_total_usd"])
            lines.append(
                f"  best: {best['window_days']}d → "
                f"${best['round_trip_total_usd']:.0f} round-trip "
                f"(return {best['return_date']})"
            )
            for o in options:
                if o["round_trip_total_usd"] is None:
                    lines.append(f"  {o['window_days']:>3}d: —")
                else:
                    lines.append(
                        f"  {o['window_days']:>3}d: ${o['round_trip_total_usd']:.0f}"
                    )
        for flag in report.flags:
            lines.append(f"  flag: {flag}")
        return "\n".join(lines)

    def _render_echo_section(self, report) -> str:
        payload = report.payload
        label = payload.get("label", "?")
        pct = report.verdict_input.get("price_position_pct", 0.0)
        typical = payload.get("typical_price_usd")
        lines = [
            f"<b>ECHO · price context</b> ({report.status.value}, conf {report.confidence:.2f})",
            f"  label: {label} ({pct:.1f}% of typical ${typical:.0f})"
            if isinstance(typical, (int, float))
            else f"  label: {label}",
        ]
        lodging = payload.get("lodging_signal")
        if lodging is None:
            lines.append("  lodging signal: <i>not available</i>")
        else:
            lines.append(
                f"  lodging signal: {str(lodging.get('color', '?')).upper()} "
                f"({lodging.get('weighted_pct_below', 0.0):.1f}% below typical, "
                f"n={lodging.get('sample_size', 0)})"
            )
        for flag in report.flags:
            lines.append(f"  flag: {flag}")
        return "\n".join(lines)

    def _render_india_section(self, report) -> str:
        """Dedicated INDIA section (Layer 6).

        Replaces the generic unknown-specialist fall-through line so the
        briefing surfaces the best hostel/budget option directly. Handles
        a report with no signal (no options / future-hook payload) and
        always echoes the status so prior callers still see 'stub'.
        """
        lines = [
            f"<b>INDIA · hostels and budget stays</b> "
            f"({report.status.value}, conf {report.confidence:.2f})"
        ]
        signal = report.payload.get("signal")
        if not signal:
            lines.append("  no scored options for city")
        else:
            price = signal.get("best_price_usd")
            score = signal.get("best_score")
            price_str = f"${price:.0f}/night" if isinstance(price, (int, float)) else "?"
            score_str = f"score {score:.1f}" if isinstance(score, (int, float)) else ""
            lines.append(
                f"  best: {signal.get('best_option_name', '?')} "
                f"({signal.get('best_category', '?')}) {price_str} {score_str}".rstrip()
            )
            lines.append(f"  options considered: {signal.get('options_count', 0)}")
            city_color = signal.get("lodging_color")
            if city_color:
                lines.append(f"  city lodging signal: {str(city_color).upper()}")
        for flag in report.flags:
            lines.append(f"  flag: {flag}")
        return "\n".join(lines)

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
