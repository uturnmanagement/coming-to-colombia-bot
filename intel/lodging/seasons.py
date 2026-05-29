"""Season classification + multiplier matrix for Colombia lodging.

The multipliers from the Colombia Desk builder spec:

    Mid-Apr to early Jun  LOW   = 1.2x
    Mid-Jan to mid-Apr    MID   = 1.0x
    Sep to early Dec      LOW   = 1.2x
    Jun to Aug            HIGH  = 0.85x
    Dec 15 to Jan 15      PEAK  = 0.75x
    Holy Week             PEAK  = 0.75x  (variable — overrides whichever
                                          season it falls in)

Multipliers scale the RAW pct-below-baseline before the GREEN/YELLOW/
RED color classifier compares against the thresholds. In LOW season
(multiplier 1.2x) a small raw drop is amplified — surfacing more
candidate deals when travel demand is naturally lower. In HIGH / PEAK
seasons (0.85x / 0.75x) a raw drop is attenuated — requiring a bigger
drop to qualify, because high-season prices already trend up.

Boundaries (inclusive of both endpoints unless noted):
    Jan 01 — Jan 15       PEAK   (continues from Dec)
    Jan 16 — Apr 14       MID
    Apr 15 — May 31       LOW
    Jun 01 — Aug 31       HIGH
    Sep 01 — Dec 14       LOW
    Dec 15 — Dec 31       PEAK

Holy Week (Palm Sunday through Holy Saturday — 7 days ending the day
before Easter Sunday) is computed per year via the Gauss algorithm and
applied as a PEAK override regardless of the surrounding season.
"""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from functools import lru_cache


HOLY_WEEK_DAYS = 7


class Season(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"
    PEAK = "peak"


# Spec-defined multipliers. Edits here propagate to every test.
SEASON_MULTIPLIERS: dict[Season, float] = {
    Season.LOW: 1.20,
    Season.MID: 1.00,
    Season.HIGH: 0.85,
    Season.PEAK: 0.75,
}


@lru_cache(maxsize=256)
def gauss_easter(year: int) -> date:
    """Western (Gregorian) Easter Sunday for `year` via the Gauss algorithm.

    Cached per process so Holy Week lookups are O(1) after the first.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holy_week(year: int) -> tuple[date, date]:
    """Inclusive (start, end) of Holy Week for `year`.

    Definition: Palm Sunday through Holy Saturday — the seven days
    ending the day before Easter Sunday. Both endpoints are inclusive.
    """
    easter = gauss_easter(year)
    end = easter - timedelta(days=1)
    start = end - timedelta(days=HOLY_WEEK_DAYS - 1)
    return (start, end)


def _in_holy_week(d: date) -> bool:
    start, end = holy_week(d.year)
    return start <= d <= end


def classify_season(d: date) -> Season:
    """Pick the season window that covers `d`. Holy Week always wins."""
    if _in_holy_week(d):
        return Season.PEAK

    month, day = d.month, d.day
    # PEAK — Dec 15 through Jan 15
    if (month == 12 and day >= 15) or (month == 1 and day <= 15):
        return Season.PEAK
    # MID — Jan 16 through Apr 14
    if (month == 1 and day >= 16) or month in (2, 3) \
            or (month == 4 and day <= 14):
        return Season.MID
    # LOW — Apr 15 through May 31
    if (month == 4 and day >= 15) or month == 5:
        return Season.LOW
    # HIGH — Jun 1 through Aug 31
    if month in (6, 7, 8):
        return Season.HIGH
    # LOW — Sep 1 through Dec 14
    if month in (9, 10, 11) or (month == 12 and day <= 14):
        return Season.LOW
    # Unreachable by construction; defensive default.
    return Season.MID


def season_multiplier(d: date) -> float:
    """Multiplier for a given date — the value used by the scoring engine."""
    return SEASON_MULTIPLIERS[classify_season(d)]
