"""Delta — Return Pairing specialist.

Layer 3 ships Delta as a foundation:
    - Pure return-window math + pairing engine in intel/return_pairing.
    - Specialist shell here takes an outbound observation and emits a
      SpecialistReport for Oak Street.
    - No live API calls. A placeholder fetcher serves heuristic prices.
      Live fetching is Layer 4+ work.
"""
from .specialist import Delta, placeholder_return_fetcher

__all__ = ["Delta", "placeholder_return_fetcher"]
