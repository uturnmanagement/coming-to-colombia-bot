"""Round-trip combo classification — pure, no I/O.

Phase 2.7. Combines an OUTBOUND leg color (RED / YELLOW / GREEN, from the
scanner's deal classifier) with a RETURN leg color (RED / YELLOW / GREEN,
from the return-ranking pass) into a single combo category.

Rule: a round trip is an alert-worthy travel opportunity when BOTH legs are
at least YELLOW. Any leg that is GREEN (or missing/unknown) drops the combo
to NON_QUALIFYING.

    qualifying = {RED, YELLOW} x {RED, YELLOW}  ->  "<OUTBOUND>_<RETURN>"
    everything else                             ->  "NON_QUALIFYING"

Boundary rule (matches the rest of intel/return_pairing): no network, no
clock, no logging. Pure string logic over leg colors.
"""
from __future__ import annotations

# A single leg "qualifies" when it is at least YELLOW.
QUALIFYING_COLORS = ("RED", "YELLOW")

# The five combo categories Phase 2.7 defines.
COMBO_CATEGORIES = (
    "RED_RED",
    "RED_YELLOW",
    "YELLOW_RED",
    "YELLOW_YELLOW",
    "NON_QUALIFYING",
)

NON_QUALIFYING = "NON_QUALIFYING"


def _norm(color: object) -> str:
    """Normalize a color to an upper-case token ('' when missing/unknown)."""
    return str(color).strip().upper() if color else ""


def combo_color(outbound_color: object, return_color: object) -> str:
    """Combine outbound + return leg colors into a combo category.

    Returns one of ``COMBO_CATEGORIES``. When both legs are at least YELLOW
    the result is ``"<OUTBOUND>_<RETURN>"`` (e.g. ``"YELLOW_RED"``); any
    other pairing (either leg GREEN, missing, or unrecognized) returns
    ``"NON_QUALIFYING"``.
    """
    ob = _norm(outbound_color)
    rt = _norm(return_color)
    if ob in QUALIFYING_COLORS and rt in QUALIFYING_COLORS:
        return f"{ob}_{rt}"
    return NON_QUALIFYING


def qualifies(outbound_color: object, return_color: object) -> bool:
    """True when the round trip is alert-worthy (both legs at least YELLOW)."""
    return combo_color(outbound_color, return_color) != NON_QUALIFYING
