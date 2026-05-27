"""Heartbeat decay engine.

Stage cadence (age = now - first_alert_at):
    0–4 h   -> ACTIVE   (15-minute interval)
    4–24 h  -> COOLING  (1-hour interval)
    24–48 h -> STALE    (12-hour interval)
    48 h +  -> ZOMBIE   (muted — no further heartbeats)

A heartbeat emits ONLY when:
    - a material trigger fires (price/route/color/departure — see
      trigger_rules.py), respecting the stage interval as a rate limit;
    - OR silence since the last heartbeat exceeds 12 hours (forced
      keepalive, regardless of stage interval).

ZOMBIE deals never emit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from .trigger_rules import has_material_change


MAX_SILENCE = timedelta(hours=12)


class HeartbeatStage(str, Enum):
    ACTIVE = "active"
    COOLING = "cooling"
    STALE = "stale"
    ZOMBIE = "zombie"


_STAGE_INTERVALS: dict[HeartbeatStage, timedelta] = {
    HeartbeatStage.ACTIVE: timedelta(minutes=15),
    HeartbeatStage.COOLING: timedelta(hours=1),
    HeartbeatStage.STALE: timedelta(hours=12),
    HeartbeatStage.ZOMBIE: timedelta(hours=0),  # not used; zombies mute
}


@dataclass(frozen=True)
class AlertSnapshot:
    deal_id: str
    color: str               # "green" | "yellow" | "red"
    price_usd: float
    route_signature: str     # e.g. "BWI->BOG direct" or "BWI->MIA->BOG"
    departure_at: datetime


@dataclass(frozen=True)
class HeartbeatDecision:
    should_emit: bool
    stage: HeartbeatStage
    reason: str
    age_hours: float
    silence: timedelta


def classify_stage(age_hours: float) -> HeartbeatStage:
    if age_hours < 0:
        # Defensive — treat clock-skewed deals as freshly active.
        return HeartbeatStage.ACTIVE
    if age_hours < 4:
        return HeartbeatStage.ACTIVE
    if age_hours < 24:
        return HeartbeatStage.COOLING
    if age_hours < 48:
        return HeartbeatStage.STALE
    return HeartbeatStage.ZOMBIE


def interval_for_stage(stage: HeartbeatStage) -> timedelta:
    return _STAGE_INTERVALS[stage]


def decide_heartbeat(
    *,
    previous: Optional[AlertSnapshot],
    current: AlertSnapshot,
    first_alert_at: datetime,
    last_heartbeat_at: Optional[datetime],
    now: datetime,
) -> HeartbeatDecision:
    """Return the heartbeat engine's decision for one observation."""
    age = now - first_alert_at
    age_hours = age.total_seconds() / 3600.0
    stage = classify_stage(age_hours)
    silence = (now - last_heartbeat_at) if last_heartbeat_at else timedelta.max

    if stage is HeartbeatStage.ZOMBIE:
        return HeartbeatDecision(
            should_emit=False,
            stage=stage,
            reason="zombie: deal aged past 48h",
            age_hours=age_hours,
            silence=silence,
        )

    if silence >= MAX_SILENCE:
        return HeartbeatDecision(
            should_emit=True,
            stage=stage,
            reason=f"max silence exceeded ({silence_label(silence)} >= 12h)",
            age_hours=age_hours,
            silence=silence,
        )

    changed, change_reason = has_material_change(previous, current)
    if not changed:
        return HeartbeatDecision(
            should_emit=False,
            stage=stage,
            reason=change_reason,
            age_hours=age_hours,
            silence=silence,
        )

    interval = interval_for_stage(stage)
    if silence < interval:
        return HeartbeatDecision(
            should_emit=False,
            stage=stage,
            reason=(
                f"rate-limited: stage {stage.value} interval "
                f"{interval_label(interval)}, "
                f"silence {silence_label(silence)}; trigger was "
                f"'{change_reason}'"
            ),
            age_hours=age_hours,
            silence=silence,
        )

    return HeartbeatDecision(
        should_emit=True,
        stage=stage,
        reason=f"material change: {change_reason}",
        age_hours=age_hours,
        silence=silence,
    )


def silence_label(td: timedelta) -> str:
    if td == timedelta.max:
        return "infinite"
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m"


def interval_label(td: timedelta) -> str:
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h and m:
        return f"{h}h{m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"
