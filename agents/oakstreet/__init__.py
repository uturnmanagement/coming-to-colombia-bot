"""Oak Street — master orchestrator for the Colombia Desk.

Layer 1 ships only the skeleton:
    - centralized Telegram rendering (one-voice)
    - receives alerts from the scanner
    - applies the heartbeat decay engine
    - placeholder ingestion of specialist reports (Echo / India / Juliet
      arrive in later layers)
"""
from .orchestrator import OakStreet, AlertEvent

__all__ = ["OakStreet", "AlertEvent"]

# Convenience re-exports for the Layer 3 typed-report path; importing
# from agents.oakstreet stays a single canonical entrypoint for
# downstream callers / specialists.
from agents.specialist_report import SpecialistReport, Status  # noqa: E402,F401

# NOTE: DeskPipeline is intentionally NOT re-exported here. It imports the
# specialists (Delta/Echo/India), which in turn import
# agents.oakstreet.orchestrator — importing it from this package __init__
# creates a circular import. Import it from its submodule instead:
#     from agents.oakstreet.pipeline import DeskPipeline, PipelineResult
