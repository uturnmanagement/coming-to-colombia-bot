"""Desk pipeline — the Layer 7B end-to-end integration.

Connects the four stages the earlier layers built but never ran together
in production:

    AlertEvent
       -> OakStreet.ingest_alert       (heartbeat decay + initial/heartbeat dispatch)
       -> specialists (.analyze)       (Delta / Echo / India)
       -> OakStreet.ingest_report      (cache per deal+agent)
       -> OakStreet.dispatch_briefing  (synthesize + dispatch the briefing)

Safety: this module renders NOTHING and sends NOTHING itself. Every
outbound side effect flows through OakStreet's dispatcher, which under
`DRY_RUN=true` records to the outbox + audit log and never calls the
live sender. The pipeline is therefore hermetic and DRY_RUN-safe by
construction; it does not change any heartbeat-decay decision (it simply
forwards the event to `ingest_alert` unchanged).

Specialists are isolated: one specialist raising is logged and skipped,
never aborting the alert or the briefing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agents.delta import Delta
from agents.echo import Echo
from agents.india import India
from agents.logging_setup import get_logger
from agents.oakstreet.orchestrator import AlertEvent, OakStreet
from agents.specialist_report import SpecialistReport
from intel.heartbeat import HeartbeatDecision

log = get_logger("pipeline")


@dataclass(frozen=True)
class PipelineResult:
    """Inspectable outcome of one event passing through the pipeline."""
    deal_id: str
    decision: Optional[HeartbeatDecision]   # None on a deal's first observation
    reports: dict                            # agent -> SpecialistReport
    briefing_text: Optional[str]
    specialist_errors: tuple = ()


@dataclass
class DeskPipeline:
    """Runs an AlertEvent through ingest -> specialists -> briefing."""
    oakstreet: OakStreet
    specialists: Optional[list] = None
    # Optional Layer 4 brain handed to India (and available for Echo).
    lodging_service: Optional[object] = None

    def __post_init__(self) -> None:
        if self.specialists is None:
            self.specialists = [
                Delta(),
                Echo(lodging_service=self.lodging_service),
                India(lodging_service=self.lodging_service),
            ]

    def process_event(
        self, event: AlertEvent, *, now: Optional[datetime] = None
    ) -> PipelineResult:
        """Drive one event through all four stages. Never raises."""
        # 1. Heartbeat decay + initial/heartbeat dispatch. Forwarded
        #    unchanged so decay behavior is identical to calling
        #    ingest_alert directly (heartbeat parity).
        decision = self.oakstreet.ingest_alert(event)

        # 2-3. Specialists analyze, then feed Oak Street. Isolated.
        reports: dict = {}
        errors: list = []
        for sp in self.specialists:
            label = getattr(sp, "__class__", type(sp)).__name__.lower()
            try:
                report: SpecialistReport = sp.analyze(event)
            except Exception as exc:  # noqa: BLE001 — one bad specialist must not abort
                log.exception("specialist %s failed", label)
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            self.oakstreet.ingest_report(report)
            reports[report.agent] = report

        # 4. Synthesize + dispatch the briefing (kind='heartbeat').
        #    DRY_RUN keeps this record-only.
        briefing = self.oakstreet.dispatch_briefing(
            event.deal_id,
            color=event.color,
            route_signature=event.route_signature,
            now=now,
        )

        return PipelineResult(
            deal_id=event.deal_id,
            decision=decision,
            reports=reports,
            briefing_text=briefing,
            specialist_errors=tuple(errors),
        )
