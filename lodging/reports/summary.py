"""Lodging summary text rendering (Phase 6A).

Pure text formatting over a CityLodgingSummary. Produces the aligned
table the desk attaches to a Delta Return Optimizer report:

    Type                  Nightly        Weekly (7n)        Monthly (30n)

with a best-value callout and an explicit MOCK-DATA disclaimer. Mirrors
the Delta renderer's honesty rule — mock estimates are always labelled.
"""
from __future__ import annotations

from lodging.lodging_models import CityLodgingSummary, LodgingEstimate, StayEstimate

_COL_TYPE = 21
_COL_NIGHTLY = 15
_COL_WEEKLY = 18


def _band(low: float, high: float) -> str:
    return f"${low:,.0f}–${high:,.0f}"


def _stay_cell(est: StayEstimate, show_discount: bool) -> str:
    band = _band(est.low_usd, est.high_usd)
    if show_discount and est.discount_pct > 0:
        return f"{band} (-{est.discount_pct * 100:.0f}%)"
    return band


def _row(est: LodgingEstimate) -> str:
    name = est.accommodation.label
    nightly = _stay_cell(est.nightly, show_discount=False)
    weekly = _stay_cell(est.weekly, show_discount=True)
    monthly = _stay_cell(est.monthly, show_discount=True)
    star = "   ★ BEST VALUE" if est.is_best_value else ""
    return (
        f"{name:<{_COL_TYPE}}{nightly:<{_COL_NIGHTLY}}"
        f"{weekly:<{_COL_WEEKLY}}{monthly}{star}"
    )


def render_city_summary(summary: CityLodgingSummary) -> str:
    """Render one city's lodging summary as an aligned text block."""
    lines = [
        f"LODGING INTELLIGENCE — {summary.city}",
    ]
    if summary.is_mock:
        lines.append(
            "mock estimates (Phase 6A) — illustrative, NOT live pricing"
        )
    lines.append(summary.provider_note)
    lines.append("")
    lines.append(
        f"{'Type':<{_COL_TYPE}}{'Nightly':<{_COL_NIGHTLY}}"
        f"{'Weekly (7n)':<{_COL_WEEKLY}}Monthly (30n)"
    )

    if not summary.estimates:
        lines.append("  no lodging estimates available for this city")
        return "\n".join(lines).rstrip() + "\n"

    for est in summary.estimates:
        lines.append(_row(est))

    best = summary.best_value
    if best is not None:
        lines.append("")
        lines.append(
            f"Best value: {best.accommodation.label} — "
            f"~${best.nightly.mid_usd:,.0f}/night, "
            f"~${best.weekly.mid_usd:,.0f}/week, "
            f"~${best.monthly.mid_usd:,.0f}/month"
        )
    return "\n".join(lines).rstrip() + "\n"
