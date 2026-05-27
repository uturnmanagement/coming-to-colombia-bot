"""Echo — Price-context specialist (lodging hook reserved).

Layer 3 ships Echo as a foundation shell:
    - Calls the pure price-context classifier to label the observed
      fare against a typical-price band.
    - Emits a SpecialistReport with `price_position_label` and
      `price_position_pct` in verdict_input.
    - Reserves `lodging_signal` in verdict_input for the future
      lodging-intelligence layer (Airbnb / Apify — explicitly NOT
      Layer 3). The reservation lives in agents.specialist_report
      VERDICT_KEYS so Layer 4 can attach without renegotiating the
      schema.

Echo never makes external HTTP calls in Layer 3.
"""
from .specialist import Echo, DEFAULT_TYPICAL_PRICE_USD

__all__ = ["Echo", "DEFAULT_TYPICAL_PRICE_USD"]
