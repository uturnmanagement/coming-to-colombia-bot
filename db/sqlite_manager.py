"""SQLite manager for Colombia Desk orchestration state.

Honors DRY_RUN: when enabled, opens an in-memory database (`:memory:`)
so simulations exercise the full code path without touching disk.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


class SqliteManager:
    def __init__(self, db_path: Path | str, dry_run: bool = False):
        self.dry_run = dry_run
        self.db_path = ":memory:" if dry_run else str(db_path)
        if not dry_run:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._apply_schema()

    def _apply_schema(self) -> None:
        with SCHEMA_FILE.open("r", encoding="utf-8") as fh:
            self._conn.executescript(fh.read())

    @contextmanager
    def cursor(self):
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()

    # --- deals ------------------------------------------------------------

    def upsert_deal(
        self,
        deal_id: str,
        first_alert_at: datetime,
        color: str,
        price_usd: float,
        route_signature: str,
        departure_at: datetime,
        now: datetime,
    ) -> None:
        # The initial alert is heartbeat zero — anchor `last_heartbeat_at`
        # to `first_alert_at` so the decay engine measures silence from
        # the moment the deal was first announced. heartbeat_count stays
        # at 0; the count tracks *follow-up* heartbeats only.
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO deals (
                    deal_id, first_alert_at, last_heartbeat_at,
                    heartbeat_count, status,
                    last_color, last_price_usd, last_route_signature,
                    last_departure_at, updated_at
                ) VALUES (?, ?, ?, 0, 'active', ?, ?, ?, ?, ?)
                ON CONFLICT(deal_id) DO UPDATE SET
                    last_color = excluded.last_color,
                    last_price_usd = excluded.last_price_usd,
                    last_route_signature = excluded.last_route_signature,
                    last_departure_at = excluded.last_departure_at,
                    updated_at = excluded.updated_at
                """,
                (
                    deal_id,
                    first_alert_at.isoformat(),
                    first_alert_at.isoformat(),
                    color,
                    price_usd,
                    route_signature,
                    departure_at.isoformat(),
                    now.isoformat(),
                ),
            )

    def update_after_heartbeat(
        self,
        deal_id: str,
        heartbeat_at: datetime,
        stage: str,
        color: str,
        price_usd: float,
        route_signature: str,
        departure_at: datetime,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE deals SET
                    last_heartbeat_at = ?,
                    heartbeat_count = heartbeat_count + 1,
                    status = ?,
                    last_color = ?,
                    last_price_usd = ?,
                    last_route_signature = ?,
                    last_departure_at = ?,
                    updated_at = ?
                WHERE deal_id = ?
                """,
                (
                    heartbeat_at.isoformat(),
                    stage,
                    color,
                    price_usd,
                    route_signature,
                    departure_at.isoformat(),
                    heartbeat_at.isoformat(),
                    deal_id,
                ),
            )

    def mark_stage(self, deal_id: str, stage: str, now: datetime) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE deals SET status = ?, updated_at = ? WHERE deal_id = ?",
                (stage, now.isoformat(), deal_id),
            )

    def get_deal(self, deal_id: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            row = cur.execute(
                "SELECT * FROM deals WHERE deal_id = ?", (deal_id,)
            ).fetchone()
        return dict(row) if row else None

    # --- snapshots --------------------------------------------------------

    def insert_snapshot(
        self,
        deal_id: str,
        emitted_at: datetime,
        stage: str,
        color: str,
        price_usd: float,
        route_signature: str,
        departure_at: datetime,
        trigger_reason: str,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO heartbeat_snapshots (
                    deal_id, emitted_at, stage, color, price_usd,
                    route_signature, departure_at, trigger_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deal_id,
                    emitted_at.isoformat(),
                    stage,
                    color,
                    price_usd,
                    route_signature,
                    departure_at.isoformat(),
                    trigger_reason,
                ),
            )

    def snapshots_for(self, deal_id: str) -> Iterable[dict[str, Any]]:
        with self.cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM heartbeat_snapshots WHERE deal_id = ? "
                "ORDER BY emitted_at",
                (deal_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- specialist reports (placeholder for Layer 2+) -------------------

    def insert_specialist_report(
        self,
        specialist: str,
        report_at: datetime,
        payload_json: str,
        deal_id: str | None = None,
    ) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO specialist_reports
                    (deal_id, specialist, report_at, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (deal_id, specialist, report_at.isoformat(), payload_json),
            )

    def specialist_reports_for(self, deal_id: str) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM specialist_reports WHERE deal_id = ? "
                "ORDER BY report_at",
                (deal_id,),
            ).fetchall()
        return [dict(r) for r in rows]
