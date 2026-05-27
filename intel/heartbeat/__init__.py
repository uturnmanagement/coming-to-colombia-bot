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
from .trigger_rules import has_material_change

__all__ = [
    "AlertSnapshot",
    "HeartbeatDecision",
    "HeartbeatStage",
    "classify_stage",
    "decide_heartbeat",
    "interval_for_stage",
    "has_material_change",
]
