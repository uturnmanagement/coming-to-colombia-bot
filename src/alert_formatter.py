"""Format Telegram messages for deals, summaries, and heartbeats.

All output uses Telegram HTML parse mode. City labels and the region
name come from the active region pack, so messages read correctly for
any market.
"""
from __future__ import annotations

from datetime import datetime

from . import region
from .deal_classifier import DealColor, DealResult


def _emoji(color: str) -> str:
    return region.DEAL_COLOR_EMOJI.get(color, "")


def esc(text) -> str:
    """Escape text for Telegram HTML parse mode."""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


# --- Tier 2 return-optimizer enrichment (display-only, dict-driven) ---------
#
# These helpers read the Delta specialist payload dict (already JSON-safe;
# see agents/delta/specialist.py:_option_to_dict). Nothing is synthesized:
# flight numbers and connection airports render ONLY when a provider supplied
# them, the source badge reads LIVE only for a provably-live option, and the
# booking link is a guarded BONUS — shown only when the option is live AND
# carries a validated http(s) URL. A non-empty booking_url only ever comes
# from live Skyscanner, so it never appears on placeholder/MOCK data.

_BOOKING_URL_SCHEMES = ("https://", "http://")
_UNSAFE_URL_CHARS = set(" \t\r\n\"'<>`")


def _is_safe_booking_url(url) -> bool:
    """True only for a well-formed http(s) link safe to embed in an href."""
    if not isinstance(url, str):
        return False
    u = url.strip()
    for scheme in _BOOKING_URL_SCHEMES:
        if u.lower().startswith(scheme) and len(u) > len(scheme):
            return all(c not in _UNSAFE_URL_CHARS for c in u)
    return False


def _ret_source_badge(option: dict) -> str:
    """LIVE only for a provably-live option; everything else is MOCK."""
    return "LIVE" if str(option.get("source", "")).lower() == "live" else "MOCK"


def _ret_booking_link(option: dict):
    """A guarded booking link: live source + existing + valid URL, else None."""
    if str(option.get("source", "")).lower() != "live":
        return None
    url = str(option.get("booking_url") or "").strip()
    if not _is_safe_booking_url(url):
        return None
    return f'<a href="{esc(url)}">Book this return</a>'


def _best_priced_return(payload: dict):
    """The cheapest fully-priced return option dict, or None."""
    options = payload.get("options") or []
    priced = [
        o for o in options
        if isinstance(o, dict) and o.get("round_trip_total_usd") is not None
    ]
    if not priced:
        return None
    return min(priced, key=lambda o: o["round_trip_total_usd"])


def format_return_block(payload: dict) -> list[str]:
    """Tier 2 itinerary enrichment for the best priced return option.

    Returns Telegram-HTML lines to append to the return-pairing section, or
    [] when there is no priced return to enrich (the caller still prints its
    own "no priced return windows" line in that case).
    """
    best = _best_priced_return(payload)
    if best is None:
        return []

    lines: list[str] = []
    route_type = str(best.get("route_type") or "").strip()
    if route_type:
        lines.append(f"  ↳ <b>Return route:</b> {esc(route_type)}")

    airline = str(best.get("airline") or "").strip()
    if airline:
        lines.append(f"  ↳ <b>Airline:</b> {esc(airline)}")

    flights = [str(f) for f in (best.get("flight_numbers") or []) if f]
    if flights:
        lines.append(f"  ↳ <b>Flights:</b> {esc(', '.join(flights))}")

    connections = [str(c) for c in (best.get("connections") or []) if c]
    if connections:
        lines.append(f"  ↳ <b>Connections:</b> {esc(', '.join(connections))}")

    lines.append(f"  ↳ <b>Source:</b> {_ret_source_badge(best)}")

    link = _ret_booking_link(best)
    if link:
        lines.append(f"  ↳ {link}")
    return lines


def _route_lines(result: DealResult) -> list[str]:
    comp = result.comparison
    lines: list[str] = []
    if comp.direct:
        lines.append(
            f"• Direct: <b>${comp.direct.total_price:,.0f}</b> "
            f"({comp.direct.travel_duration_hours:.0f}h travel)"
        )
    if comp.positioning:
        p = comp.positioning
        lines.append(
            f"• Positioning via {esc(region.city_label(p.gateway))}: "
            f"<b>${p.total_price:,.0f}</b> "
            f"({p.travel_duration_hours:.0f}h travel, {p.layover_hours:.0f}h layover)"
        )
    return lines


def format_deal_alert(result: DealResult) -> str:
    """A single YELLOW/RED deal alert."""
    cls = result.classification
    comp = result.comparison
    rec = comp.recommended
    head = "🔥 RED DEAL" if cls.color == DealColor.RED else "✨ Strong deal"

    lines = [
        f"{_emoji(cls.color.value)} <b>{head} — "
        f"{esc(region.city_label(comp.destination))}</b>",
        "",
    ]
    if rec is not None:
        lines += [
            f"<b>Book:</b> {esc(rec.describe())}",
            f"<b>Price:</b> ${rec.total_price:,.0f}",
            f"<b>Departs:</b> {rec.depart_dt:%a %b %d, %H:%M}",
            f"<b>Arrives:</b> {rec.final_arrival_dt:%a %b %d, %H:%M}",
        ]
    if cls.effective_savings_usd > 0:
        lines.append(f"<b>Savings:</b> ${cls.effective_savings_usd:,.0f}")
    lines += ["", *_route_lines(result), ""]
    lines.append(f"<b>Urgency:</b> {cls.urgency_score:.0f}/100")
    lines += ["", esc(cls.explanation)]
    if result.arrival.warning:
        lines += ["", esc(result.arrival.warning)]
    return "\n".join(lines).strip()


def format_heartbeat_alert(
    result: DealResult, pulse: int, elapsed_minutes: float, past_window: bool
) -> str:
    """A repeated RED-deal heartbeat ping."""
    cls = result.classification
    comp = result.comparison
    rec = comp.recommended
    window = " · beyond the alert window, still RED" if past_window else ""
    lines = [
        f"🔴 <b>RED DEAL STILL LIVE — "
        f"{esc(region.city_label(comp.destination))}</b>",
        f"<i>Heartbeat #{pulse} · {elapsed_minutes:.0f} min since first alert"
        f"{window}</i>",
        "",
    ]
    if rec is not None:
        lines += [
            f"<b>Book:</b> {esc(rec.describe())}",
            f"<b>Price:</b> ${rec.total_price:,.0f}",
            f"<b>Savings:</b> ${cls.effective_savings_usd:,.0f}",
            f"<b>Departs:</b> {rec.depart_dt:%a %b %d, %H:%M}",
        ]
    if result.arrival.warning:
        lines += ["", esc(result.arrival.warning)]
    return "\n".join(lines)


def format_heartbeat_end(destination: str, reason: str) -> str:
    return (
        f"⏹️ <b>Heartbeat ended — {esc(region.city_label(destination))}</b>\n"
        f"{esc(reason)}"
    )


def _deal_line(result: DealResult) -> str:
    cls = result.classification
    comp = result.comparison
    rec = comp.recommended
    emoji = _emoji(cls.color.value)
    if rec is None:
        return (
            f"{emoji} <b>{esc(region.city_label(comp.destination))}</b> "
            "— no flights found"
        )
    routing = "positioning" if comp.recommend_positioning else "direct"
    extra = (
        f" · save ${cls.effective_savings_usd:,.0f}"
        if cls.effective_savings_usd > 0
        else ""
    )
    return (
        f"{emoji} <b>{esc(region.city_label(comp.destination))}</b> — "
        f"${rec.total_price:,.0f} ({routing}){extra} · "
        f"urgency {cls.urgency_score:.0f}"
    )


def format_deals_list(
    results: list[DealResult],
    color_filter: DealColor | None = None,
    title: str = "Latest flight deals",
) -> str:
    if not results:
        return "No scan has completed yet. Try again in a minute."
    shown = [r for r in results if color_filter is None or r.color == color_filter]
    if not shown:
        name = color_filter.value if color_filter else ""
        return f"No {name} deals in the latest scan."
    lines = [f"<b>{esc(title)}</b>", ""]
    for r in shown:
        lines.append(_deal_line(r))
    return "\n".join(lines)


def format_destination_detail(result: DealResult) -> str:
    cls = result.classification
    comp = result.comparison
    lines = [
        f"{_emoji(cls.color.value)} "
        f"<b>{esc(region.city_label(comp.destination))} — {cls.color.value}</b>",
        "",
        *(_route_lines(result) or ["No flights found."]),
        "",
    ]
    if comp.recommended is not None:
        rec = comp.recommended
        lines += [
            f"<b>Recommended:</b> {esc(rec.describe())}",
            f"<b>Departs:</b> {rec.depart_dt:%a %b %d, %H:%M}",
            f"<b>Arrives:</b> {rec.final_arrival_dt:%a %b %d, %H:%M}",
        ]
    lines += ["", f"<b>Urgency:</b> {cls.urgency_score:.0f}/100", esc(cls.explanation)]
    if result.arrival.warning:
        lines += ["", esc(result.arrival.warning)]
    for note in cls.notes:
        lines.append("• " + esc(note))
    return "\n".join(lines)


def format_positioning_report(results: list[DealResult]) -> str:
    lines = [
        "<b>🛫 Positioning route analysis</b>",
        "<i>Direct fare vs. cheapest origin -> gateway -> destination route.</i>",
        "",
    ]
    any_row = False
    for r in results:
        comp = r.comparison
        if not comp.direct or not comp.positioning:
            continue
        any_row = True
        verdict = "✅ worth it" if comp.recommend_positioning else "➖ skip"
        lines.append(
            f"<b>{esc(region.city_label(comp.destination))}</b>\n"
            f"  Direct ${comp.direct.total_price:,.0f}  |  "
            f"Via {esc(comp.positioning.gateway)} "
            f"${comp.positioning.total_price:,.0f}  |  "
            f"Δ ${comp.positioning_savings:,.0f}  {verdict}"
        )
    if not any_row:
        lines.append("No comparable routes in the latest scan.")
    return "\n".join(lines)


def format_daily_summary(results: list[DealResult], scan_time: datetime) -> str:
    pack = region.active()
    counts = {c: 0 for c in DealColor}
    for r in results:
        counts[r.color] += 1
    lines = [
        f"<b>📅 Daily airfare digest — {esc(pack.origin_label)} "
        f"-> {esc(pack.name)}</b>",
        f"<i>{scan_time:%A %b %d, %Y · %H:%M}</i>",
        "",
        f"🔴 {counts[DealColor.RED]} red · "
        f"🟡 {counts[DealColor.YELLOW]} yellow · "
        f"🟢 {counts[DealColor.GREEN]} green",
        "",
    ]
    for r in sorted(
        results, key=lambda x: x.classification.urgency_score, reverse=True
    ):
        lines.append(_deal_line(r))
    lines += ["", "Use /deals, /positioning or a city command for details."]
    return "\n".join(lines)


def format_status(
    config,
    last_scan: datetime | None,
    results: list[DealResult],
    active_red: int,
) -> str:
    pack = config.region
    lines = ["<b>📡 Airfare Intelligence — status</b>", ""]
    if pack is not None:
        lines.append(f"<b>Region:</b> {esc(pack.name)} ({esc(config.region_pack)})")
        lines.append(f"<b>Origin:</b> {esc(pack.origin_label)}")
    lines.append(f"<b>Data source:</b> {esc(config.flight_api_provider)}")
    if last_scan is not None:
        lines.append(f"<b>Last scan:</b> {last_scan:%b %d, %H:%M}")
    else:
        lines.append("<b>Last scan:</b> not yet run")
    if results:
        counts = {c: 0 for c in DealColor}
        for r in results:
            counts[r.color] += 1
        lines.append(
            f"<b>Latest deals:</b> 🔴 {counts[DealColor.RED]}  "
            f"🟡 {counts[DealColor.YELLOW]}  🟢 {counts[DealColor.GREEN]}"
        )
    lines.append(f"<b>Active RED heartbeats:</b> {active_red}")
    lines.append(f"<b>Recheck:</b> every {config.yellow_recheck_minutes} min")
    lines.append(
        f"<b>RED heartbeat:</b> every {config.red_heartbeat_minutes} min "
        f"for {config.red_heartbeat_duration_hours}h"
    )
    return "\n".join(lines)
