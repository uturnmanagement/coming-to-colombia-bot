"""Return-window date arithmetic and mode resolution.

The canonical Colombia Desk return-window list is:

    4, 7, 10, 14, 21, 30, 42, 50 days

Short-stay (4–14) covers weekends and short vacations; mid-stay
(21–30) is the most common returning-citizen window; long-stay
(42–50) tracks digital-nomad / extended-family stays. Adding or
removing a window is a deliberate product decision — do it here
and the Delta specialist + every test re-derives.

Layer 3 enhancement
-------------------
`resolve_return_windows()` reads the operator's environment and
returns the active window tuple:

    RETURN_WINDOW_MODE        "fixed" (default) | "range"
    RETURN_WINDOWS_DAYS       fixed-mode override; e.g. "4,7,10,14"
    RETURN_MIN_DAYS           range-mode lower bound (default 4)
    RETURN_MAX_DAYS           range-mode upper bound (default 60)
    RETURN_WINDOW_STEP_DAYS   range-mode step (default 1)

The default is `fixed` so an upgrade is non-breaking. `range` mode
exists for exhaustive scans across consecutive return dates (every
day from 4 through 60 by default).
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from enum import Enum
from typing import Iterable, Tuple


RETURN_WINDOWS_DAYS: Tuple[int, ...] = (4, 7, 10, 14, 21, 30, 42, 50)


class ReturnWindowMode(str, Enum):
    FIXED = "fixed"
    RANGE = "range"


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


def parse_fixed_list(raw: str) -> Tuple[int, ...]:
    """Parse a comma-separated list of return-window day counts.

    Empty entries are skipped; whitespace is tolerated. Order and
    duplicates from the input are preserved (the caller decides
    whether to dedupe).
    """
    days: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError as exc:
            raise ValueError(
                f"RETURN_WINDOWS_DAYS contains non-integer entry {part!r}"
            ) from exc
        if n <= 0:
            raise ValueError(f"return window must be positive: {n}")
        days.append(n)
    if not days:
        raise ValueError("RETURN_WINDOWS_DAYS resolved to an empty list")
    return tuple(days)


def range_windows(
    min_days: int, max_days: int, step: int = 1
) -> Tuple[int, ...]:
    """Generate (min_days, min_days+step, ..., max_days) inclusive of both
    endpoints when the step lines up.

    Range-mode default of (4, 60, 1) yields 57 windows: every integer
    from 4 through 60 inclusive.
    """
    if min_days < 1:
        raise ValueError(f"RETURN_MIN_DAYS must be >= 1, got {min_days}")
    if max_days < min_days:
        raise ValueError(
            f"RETURN_MAX_DAYS ({max_days}) must be >= RETURN_MIN_DAYS "
            f"({min_days})"
        )
    if step < 1:
        raise ValueError(f"RETURN_WINDOW_STEP_DAYS must be >= 1, got {step}")
    return tuple(range(min_days, max_days + 1, step))


def resolve_return_windows(env: dict[str, str] | None = None) -> Tuple[int, ...]:
    """Pick the active window list based on environment configuration.

    Defaults preserve Layer 3's canonical behavior: no env vars set →
    the original 8-window list. Pass `env={...}` to test resolution
    against an injected mapping without touching `os.environ`.
    """
    src = env if env is not None else os.environ
    mode_raw = src.get("RETURN_WINDOW_MODE", ReturnWindowMode.FIXED.value)
    try:
        mode = ReturnWindowMode(mode_raw.strip().lower())
    except ValueError as exc:
        raise ValueError(
            f"RETURN_WINDOW_MODE must be 'fixed' or 'range', got {mode_raw!r}"
        ) from exc

    if mode is ReturnWindowMode.RANGE:
        lo = int(src.get("RETURN_MIN_DAYS", "4"))
        hi = int(src.get("RETURN_MAX_DAYS", "60"))
        step = int(src.get("RETURN_WINDOW_STEP_DAYS", "1"))
        return range_windows(lo, hi, step)

    # fixed mode
    raw = src.get("RETURN_WINDOWS_DAYS")
    if raw:
        return parse_fixed_list(raw)
    return RETURN_WINDOWS_DAYS
