"""Color-driven heartbeat policy (Phase 2.8).

The decay engine (``decay_engine.py``) classifies a deal's *age* into
stages and detects *material change*. This module sits on top of it and
becomes the **authoritative governor** of whether a follow-up heartbeat
actually emits, driven by the deal's COLOR rather than its age:

    RED     alert immediately, then heartbeat every 3 hours,
            stop after 48 hours, at most 16 heartbeat reminders.
    YELLOW  alert immediately, then heartbeat every 12 hours,
            stop after 48 hours, at most 4 heartbeat reminders.
    GREEN   no heartbeat, no alert.

Reactivation — a deal that is rate-limited or has hit its reminder cap
emits anyway (within the 48-hour lifetime) when something genuinely new
happens:

    - the color upgrades (e.g. YELLOW -> RED),
    - the price improves materially (drops >= $5),
    - the route changes,
    - the departure or return date changes.

A brand-new ``deal_id`` is a *different* deal: it restarts at its first
alert through the orchestrator's first-observation path, not here.

Reactivation bypasses both the cadence interval and the reminder cap
because each reactivation carries new information — caps exist to stop
*identical* keep-alive spam, not to swallow a better deal. The 48-hour
lifetime is the hard ceiling: past it the deal is a zombie and only a
new ``deal_id`` revives it.

Duplicate suppression — two observations of the same deal that share the
same ``(deal_id, route, departure date, return date, total price)``
fingerprint carry no new information; the only thing that may still emit
for them is a scheduled cadence keep-alive. ``deal_fingerprint`` builds
that key and ``is_duplicate`` compares two of them; the reactivation
rules above are the exact negation of a duplicate.

Round-trip combos — a qualifying combo (both legs >= YELLOW, see
``intel.return_pairing.combo``) is governed by the same policy at the
urgency of its strongest leg (RED if either leg is RED, else YELLOW).
Any combo containing GREEN or missing color data is non-qualifying and
never heartbeats, exactly like a GREEN single leg.

Pure module: no network, no clock, no logging. ``now`` is always passed
in so the policy is fully deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from intel.return_pairing.combo import combo_color, qualifies

# --- policy constants --------------------------------------------------------

STOP_AFTER_HOURS = 48.0
STOP_AFTER = timedelta(hours=STOP_AFTER_HOURS)

# A price "improves materially" when it drops by at least this much.
MATERIAL_PRICE_IMPROVEMENT_USD = 5.0

# Ordering for color-upgrade detection. Higher = more urgent.
_COLOR_RANK = {"green": 1, "yellow": 2, "red": 3}


@dataclass(frozen=True)
class ColorSpec:
    interval: timedelta      # minimum spacing between cadence heartbeats
    max_reminders: int       # cap on routine (non-reactivation) heartbeats


# RED and YELLOW have heartbeats; GREEN deliberately has no entry.
_SPECS: dict[str, ColorSpec] = {
    "red": ColorSpec(interval=timedelta(hours=3), max_reminders=16),
    "yellow": ColorSpec(interval=timedelta(hours=12), max_reminders=4),
}


@dataclass(frozen=True)
class PolicyDecision:
    should_emit: bool
    reason: str
    color: str               # normalized lower-case color the policy used
    is_reactivation: bool = False
    stopped: bool = False     # past the 48h lifetime
    cap_reached: bool = False  # hit the reminder cap (and not reactivating)
    age_hours: float = 0.0
    silence: timedelta = timedelta(0)


# --- color helpers -----------------------------------------------------------

def _norm(color: object) -> str:
    return str(color).strip().lower() if color else ""


def _rank(color: object) -> int:
    return _COLOR_RANK.get(_norm(color), 0)


def heartbeats_for(color: object) -> bool:
    """True when this color participates in the heartbeat policy at all."""
    return _norm(color) in _SPECS


# --- reactivation + duplicate fingerprint ------------------------------------

def reactivation_reason(
    previous,
    current,
    *,
    prev_return_date: Optional[date] = None,
    curr_return_date: Optional[date] = None,
) -> Optional[str]:
    """Return a human reason if `current` is a material re-activation of
    `previous`, else None. `previous`/`current` are AlertSnapshots.

    Order matters only for which reason is surfaced first; any single
    trigger re-activates the deal.
    """
    if previous is None:
        return None

    if _rank(current.color) > _rank(previous.color):
        return (
            f"color upgrade {_norm(previous.color).upper()}"
            f"->{_norm(current.color).upper()}"
        )

    drop = float(previous.price_usd) - float(current.price_usd)
    if drop >= MATERIAL_PRICE_IMPROVEMENT_USD:
        return (
            f"price improved ${previous.price_usd:.0f}->${current.price_usd:.0f} "
            f"(-${drop:.0f} >= ${MATERIAL_PRICE_IMPROVEMENT_USD:.0f})"
        )

    if previous.route_signature != current.route_signature:
        return (
            f"route {previous.route_signature!r}->{current.route_signature!r}"
        )

    if previous.departure_at.date() != current.departure_at.date():
        return (
            f"departure date {previous.departure_at.date()}"
            f"->{current.departure_at.date()}"
        )

    if prev_return_date != curr_return_date:
        return f"return date {prev_return_date}->{curr_return_date}"

    return None


def deal_fingerprint(
    deal_id: str,
    route_signature: str,
    departure_at,
    return_date,
    total_price_usd: float,
) -> str:
    """Stable identity key over the five fields that define a distinct
    round-trip opportunity: deal_id, route, departure date, return date,
    total price. Two observations with the same fingerprint are duplicates.
    """
    dep = (
        departure_at.date().isoformat()
        if isinstance(departure_at, datetime)
        else (departure_at.isoformat() if isinstance(departure_at, date) else str(departure_at))
    )
    if isinstance(return_date, datetime):
        ret = return_date.date().isoformat()
    elif isinstance(return_date, date):
        ret = return_date.isoformat()
    elif return_date in (None, ""):
        ret = "-"
    else:
        ret = str(return_date)
    return f"{deal_id}|{route_signature}|{dep}|{ret}|{float(total_price_usd):.2f}"


def is_duplicate(prev_fingerprint: Optional[str], curr_fingerprint: str) -> bool:
    """True when two fingerprints are identical (no new information)."""
    return prev_fingerprint is not None and prev_fingerprint == curr_fingerprint


# --- combo -> effective heartbeat color --------------------------------------

def combo_heartbeat_color(outbound_color: object, return_color: object) -> Optional[str]:
    """Effective heartbeat color for a round-trip combo, or None when the
    combo does not qualify (any GREEN/missing leg -> no heartbeat).

    A qualifying combo (both legs >= YELLOW) heartbeats at the urgency of
    its strongest leg: RED if either leg is RED, otherwise YELLOW.
    """
    if not qualifies(outbound_color, return_color):
        return None
    category = combo_color(outbound_color, return_color)  # e.g. "RED_YELLOW"
    return "red" if "RED" in category.split("_") else "yellow"


# --- the decision ------------------------------------------------------------

def decide_policy_heartbeat(
    *,
    color: object,
    previous,
    current,
    first_alert_at: datetime,
    last_heartbeat_at: Optional[datetime],
    now: datetime,
    heartbeat_count: int,
    prev_return_date: Optional[date] = None,
    curr_return_date: Optional[date] = None,
) -> PolicyDecision:
    """Authoritative decision for one follow-up observation of a deal.

    The first observation of a deal is handled by the caller (it always
    emits a normal alert, never a heartbeat); this function governs every
    *subsequent* observation.
    """
    norm = _norm(color)
    age = now - first_alert_at
    age_hours = age.total_seconds() / 3600.0
    silence = (now - last_heartbeat_at) if last_heartbeat_at else timedelta.max

    spec = _SPECS.get(norm)
    if spec is None:
        # GREEN, or missing/unknown color -> never heartbeats.
        label = norm.upper() if norm else "unknown"
        return PolicyDecision(
            should_emit=False,
            reason=f"{label}: no heartbeat (GREEN/unknown never pings)",
            color=norm,
            age_hours=age_hours,
            silence=silence,
        )

    # Hard 48h lifetime ceiling — only a new deal_id (handled upstream as a
    # first observation) revives a deal past this point.
    if age >= STOP_AFTER:
        return PolicyDecision(
            should_emit=False,
            reason=f"stopped: aged {age_hours:.1f}h past {STOP_AFTER_HOURS:.0f}h lifetime",
            color=norm,
            stopped=True,
            age_hours=age_hours,
            silence=silence,
        )

    # Reactivation carries new information -> bypasses cadence + cap.
    react = reactivation_reason(
        previous, current,
        prev_return_date=prev_return_date, curr_return_date=curr_return_date,
    )
    if react is not None:
        return PolicyDecision(
            should_emit=True,
            reason=f"reactivated: {react}",
            color=norm,
            is_reactivation=True,
            age_hours=age_hours,
            silence=silence,
        )

    # Reminder cap on routine (identical-information) keep-alives.
    if heartbeat_count >= spec.max_reminders:
        return PolicyDecision(
            should_emit=False,
            reason=(
                f"cap reached: {heartbeat_count}/{spec.max_reminders} "
                f"{norm.upper()} reminders sent"
            ),
            color=norm,
            cap_reached=True,
            age_hours=age_hours,
            silence=silence,
        )

    # Cadence rate-limit.
    if silence < spec.interval:
        return PolicyDecision(
            should_emit=False,
            reason=(
                f"rate-limited: {_fmt(silence)} since last < {norm.upper()} "
                f"interval {_fmt(spec.interval)}"
            ),
            color=norm,
            age_hours=age_hours,
            silence=silence,
        )

    return PolicyDecision(
        should_emit=True,
        reason=(
            f"{norm.upper()} cadence: {_fmt(silence)} since last "
            f"(>= {_fmt(spec.interval)}); reminder "
            f"{heartbeat_count + 1}/{spec.max_reminders}"
        ),
        color=norm,
        age_hours=age_hours,
        silence=silence,
    )


def _fmt(td: timedelta) -> str:
    if td == timedelta.max:
        return "infinite"
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h and m:
        return f"{h}h{m:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"
