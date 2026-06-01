"""Heartbeat decay engine — stage classification + trigger evaluation.

Exports:
    HeartbeatStage          enum
    AlertSnapshot           dataclass (the observable state of a deal)
    HeartbeatDecision       dataclass (the engine's output)
    classify_stage          age_hours -> stage
    decide_heartbeat        full evaluation
"""
from .decay_engine import (
    AlertSnapshot,
    HeartbeatDecision,
    HeartbeatStage,
    classify_stage,
    decide_heartbeat,
    interval_for_stage,
)
from .policy import (
    MATERIAL_PRICE_IMPROVEMENT_USD,
    STOP_AFTER,
    STOP_AFTER_HOURS,
    PolicyDecision,
    combo_heartbeat_color,
    deal_fingerprint,
    decide_policy_heartbeat,
    heartbeats_for,
    is_duplicate,
    reactivation_reason,
)
from .trigger_rules import has_material_change

__all__ = [
    "AlertSnapshot",
    "HeartbeatDecision",
    "HeartbeatStage",
    "classify_stage",
    "decide_heartbeat",
    "interval_for_stage",
    "has_material_change",
    # Phase 2.8 color-driven policy.
    "PolicyDecision",
    "decide_policy_heartbeat",
    "reactivation_reason",
    "deal_fingerprint",
    "is_duplicate",
    "combo_heartbeat_color",
    "heartbeats_for",
    "STOP_AFTER",
    "STOP_AFTER_HOURS",
    "MATERIAL_PRICE_IMPROVEMENT_USD",
]
