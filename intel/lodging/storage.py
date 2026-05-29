"""Lodging-specific SQLite operations.

Wraps the existing `db.sqlite_manager.SqliteManager` connection. The
new tables (`lodging_baseline`, `lodging_history`) live in the same
SQLite file as the deals + heartbeat_snapshots tables — single source
of truth.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, Optional

from db.sqlite_manager import SqliteManager
from .baseline import LodgingBaseline
from .providers.interface import LodgingObservation


class LodgingStorage:
    """Lodging-specific SQLite operations."""

    def __init__(self, manager: SqliteManager):
        self.manager = manager

    # --- history ----------------------------------------------------------

    def record_observation(self, obs: LodgingObservation) -> None:
        with self.manager.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lodging_history (
                    city, neighborhood, beds, observed_at, stay_date,
                    price_usd, source, listing_ref, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.city.upper(),
                    obs.neighborhood,
                    obs.beds,
                    obs.observed_at.isoformat(),
                    obs.stay_date.isoformat(),
                    obs.price_usd,
                    obs.source,
                    obs.listing_ref,
                    json.dumps(obs.raw, default=str) if obs.raw else None,
                ),
            )

    def record_observations(self, observations: Iterable[LodgingObservation]) -> int:
        n = 0
        for obs in observations:
            self.record_observation(obs)
            n += 1
        return n

    def history_for(
        self,
        city: str,
        *,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM lodging_history WHERE city = ?"
        args: list = [city.upper()]
        if neighborhood is not None:
            sql += " AND neighborhood = ?"
            args.append(neighborhood)
        if beds is not None:
            sql += " AND beds = ?"
            args.append(beds)
        sql += " ORDER BY observed_at"
        with self.manager.cursor() as cur:
            rows = cur.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # --- baseline ---------------------------------------------------------

    def save_baseline(self, b: LodgingBaseline) -> int:
        with self.manager.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lodging_baseline (
                    city, neighborhood, beds, baseline_price_usd,
                    sample_size, lookback_days, computed_at, source_set
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    b.city.upper(),
                    b.neighborhood,
                    b.beds,
                    b.baseline_price_usd,
                    b.sample_size,
                    b.lookback_days,
                    b.computed_at.isoformat(),
                    ",".join(b.source_set) if b.source_set else None,
                ),
            )
            row = cur.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])

    def latest_baseline(
        self,
        city: str,
        *,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
    ) -> Optional[dict]:
        sql = "SELECT * FROM lodging_baseline WHERE city = ?"
        args: list = [city.upper()]
        if neighborhood is None:
            sql += " AND neighborhood IS NULL"
        else:
            sql += " AND neighborhood = ?"
            args.append(neighborhood)
        if beds is None:
            sql += " AND beds IS NULL"
        else:
            sql += " AND beds = ?"
            args.append(beds)
        sql += " ORDER BY computed_at DESC LIMIT 1"
        with self.manager.cursor() as cur:
            row = cur.execute(sql, args).fetchone()
        return dict(row) if row else None
