"""Return-window date arithmetic.

The canonical Colombia Desk return-window list is:

    4, 7, 10, 14, 21, 30, 42, 50 days

Short-stay (4–14) covers weekends and short vacations; mid-stay
(21–30) is the most common returning-citizen window; long-stay
(42–50) tracks digital-nomad / extended-family stays. Adding or
removing a window is a deliberate product decision — do it here
and the Delta specialist + every test re-derives.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Tuple


RETURN_WINDOWS_DAYS: Tuple[int, ...] = (4, 7, 10, 14, 21, 30, 42, 50)


def generate_windows(
    outbound_depart: date,
    *,
    windows: Iterable[int] = RETURN_WINDOWS_DAYS,
) -> list[tuple[int, date]]:
    """Return [(days, return_date), ...] for the configured window list.

    Pure: takes a date and returns dates. No I/O, no clock reads.
    """
    out = []
    for days in windows:
        if days <= 0:
            raise ValueError(f"return window must be positive: {days}")
        out.append((days, outbound_depart + timedelta(days=days)))
    return out
