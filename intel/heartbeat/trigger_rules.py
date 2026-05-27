"""Material-change rules for the heartbeat decay engine.

A heartbeat may emit ONLY if one of these triggers fires (or if max
silence is exceeded — handled in decay_engine.py):

    - price changes >= $5
    - route changes
    - color changes
    - departure shifts >= 30 minutes

`has_material_change(prev, curr) -> (bool, reason)` returns the *first*
trigger that fires so the operator sees a single human-readable reason
on each heartbeat.
"""
from __future__ import annotations

from datetime import timedelta

PRICE_DELTA_USD = 5.0
DEPARTURE_DELTA = timedelta(minutes=30)


def has_material_change(prev, curr) -> tuple[bool, str]:
    """Compare two AlertSnapshots; return (changed, reason)."""
    if prev is None:
        return True, "first observation"

    if prev.color != curr.color:
        return True, f"color {prev.color}->{curr.color}"

    if prev.route_signature != curr.route_signature:
        return True, f"route {prev.route_signature!r}->{curr.route_signature!r}"

    if abs(curr.price_usd - prev.price_usd) >= PRICE_DELTA_USD:
        return True, (
            f"price ${prev.price_usd:.0f}->${curr.price_usd:.0f} "
            f"(|delta| >= ${PRICE_DELTA_USD:.0f})"
        )

    dep_delta = abs((curr.departure_at - prev.departure_at).total_seconds())
    if dep_delta >= DEPARTURE_DELTA.total_seconds():
        minutes = int(dep_delta // 60)
        return True, f"departure shift {minutes}m (>= 30m)"

    return False, "no material change"
