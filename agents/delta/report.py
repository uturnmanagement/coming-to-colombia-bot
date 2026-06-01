"""Delta — OAK STREET return-optimizer report renderer.

Pure text rendering over the Delta SpecialistReport payload. No I/O, no
network. Renders the exact OAK STREET layout: full outbound detail, the
ranked return options across the sampled 4–60 day window, and a final
verdict.

Honesty rule: fields the data source did not return (flight numbers,
connection city, layover duration, cabin on the Skyscanner endpoint) are
printed as "— not provided by source". They are never faked.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

NA = "— not provided by source"

# Minimal airport -> city map for the Colombia desk's known codes. Used
# only to annotate codes the live search returns; an unknown code renders
# the bare code (never a guessed city).
_CITY = {
    "BWI": "Baltimore", "MDE": "Medellín", "BOG": "Bogotá",
    "CLO": "Cali", "CTG": "Cartagena", "BAQ": "Barranquilla",
    "SMR": "Santa Marta", "MIA": "Miami", "FLL": "Fort Lauderdale",
    "PTY": "Panama City", "JFK": "New York", "EWR": "Newark",
    "IAD": "Washington", "ATL": "Atlanta",
}

_DOT = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}


def _airport(code: Optional[str]) -> str:
    if not code:
        return "?"
    code = str(code).upper()
    city = _CITY.get(code)
    return f"{code} {city}" if city else code


def _time(iso: Optional[str]) -> str:
    if not iso:
        return NA
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except (ValueError, TypeError):
        return NA


def _date(iso: Optional[str]) -> str:
    if not iso:
        return NA
    try:
        return datetime.fromisoformat(iso).strftime("%a %Y-%m-%d")
    except (ValueError, TypeError):
        return NA


def _dur(minutes: Optional[int]) -> str:
    if not isinstance(minutes, (int, float)) or minutes <= 0:
        return NA
    h, m = divmod(int(minutes), 60)
    return f"{h}h{m:02d}m"


def _dot(color: Optional[str]) -> str:
    if not color:
        return ""
    return f"{_DOT.get(color.upper(), '⚪')} {color.upper()}"


def _money(v) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else NA


def _signed_money(v) -> str:
    if not isinstance(v, (int, float)):
        return NA
    sign = "+" if v >= 0 else "-"
    return f"{sign}${abs(v):,.0f}"


def _savings(opt: dict) -> str:
    """Round-trip savings versus the typical fare (signed; NA if no typical)."""
    v = opt.get("savings_vs_typical_usd")
    if not isinstance(v, (int, float)):
        return f"{NA} (no typical baseline)"
    base = opt.get("round_trip_typical_usd")
    base_str = f" vs typical {_money(base)}" if isinstance(base, (int, float)) else ""
    return f"{_signed_money(v)}{base_str}"


def _combo(opt: dict) -> str:
    """Combo category + qualify verdict for one return option."""
    combo = opt.get("combo_color") or "NON_QUALIFYING"
    verdict = "QUALIFIES ✅" if opt.get("qualifies") else "does not qualify"
    return f"{combo}  ({verdict})"


def _flight_numbers(nums) -> str:
    return ", ".join(nums) if nums else NA


def _connection(opt: dict) -> str:
    """Connection line honoring what the source actually returned."""
    conns = opt.get("connections") or []
    stops = opt.get("stops", 0)
    if stops <= 0:
        return "direct"
    if conns:
        return " · ".join(_airport(c) for c in conns)
    return f"{stops} stop(s) — airport not provided by source"


def render_delta_report(payload: dict) -> str:
    """Render the OAK STREET — DELTA RETURN OPTIMIZER text from a payload."""
    prov = payload.get("provenance", "placeholder")
    sampled = payload.get("sampled", False)
    src_line = (
        "data source: LIVE Skyscanner"
        if prov == "live" else
        "data source: PLACEHOLDER (offline stub — not real airline data)"
    )
    src_line += " · segment detail (flight #, connection, layover, cabin) " \
                "not provided by this endpoint"

    out = payload.get("outbound", {})
    ob_origin = out.get("origin") or payload.get("origin")
    ob_dest = out.get("destination") or payload.get("destination")

    lines = [
        "OAK STREET — DELTA RETURN OPTIMIZER",
        src_line,
        "",
        "OUTBOUND DETAILS:",
        f"Route:          {_airport(ob_origin)} → {_airport(ob_dest)}   "
        f"[{out.get('route_type', NA)}]",
        f"Departure:      {_date(out.get('depart_iso')) } "
        f"{_time(out.get('depart_iso'))}".rstrip(),
        f"Arrival:        {_date(out.get('arrive_iso'))} "
        f"{_time(out.get('arrive_iso'))}".rstrip(),
        f"Airline:        {out.get('airline') or NA}",
        f"Flight number:  {_flight_numbers(out.get('flight_numbers'))}",
        f"Aircraft:       {NA}",
        f"Connection:     {_connection(out)}",
        f"Layover:        {NA if out.get('stops') else 'none (direct)'}",
        f"Total duration: {_dur(out.get('duration_minutes'))}",
        f"Cabin:          {out.get('cabin') or 'economy (requested)'}",
        f"Price:          {_money(out.get('price_usd'))}",
        f"Color:          {_dot(out.get('color')) or NA}",
        f"Booking link:   {out.get('booking_url') or NA}",
        "",
    ]

    lines.extend(_render_combo_summary(payload))

    win = payload.get("window_count", 0)
    sample_note = " (sampled: 4–14 daily, then every few days)" if sampled else ""
    lines.append(f"RETURN OPTIONS 4–60 DAYS{sample_note}:")
    lines.append("")

    ranking = payload.get("ranking", {})
    top10 = ranking.get("top10") or []
    if not top10:
        lines.append("  no priced return windows — source returned no data")
    else:
        for i, opt in enumerate(top10, start=1):
            tag = " BEST OVERALL" if i == 1 else ""
            lines.extend(_render_option(i, opt, payload, tag))
            lines.append("")

    lines.extend(_render_verdict(payload, ranking))
    return "\n".join(lines).rstrip() + "\n"


def _render_combo_summary(payload: dict) -> list[str]:
    """ROUND-TRIP COMBO SUMMARY block (Phase 2.7).

    A round trip is alert-worthy when BOTH legs are at least YELLOW. This
    block states the outbound color, the round-trip typical baseline, how
    many windows qualify, and the single best (cheapest) qualifying combo.
    """
    ob_color = payload.get("outbound_color")
    rt_typical = payload.get("round_trip_typical_usd")
    qcount = payload.get("qualifying_count", 0)
    best = payload.get("best_qualifying")

    lines = [
        "ROUND-TRIP COMBO SUMMARY:",
        f"Outbound color:   {_dot(ob_color) or NA}",
        f"Typical (round):  {_money(rt_typical)}",
        f"Qualifying combos:{qcount} of {payload.get('window_count', 0)} windows "
        f"(both legs ≥ YELLOW)",
    ]
    if best:
        lines.extend([
            f"Best combo:       {best.get('combo_color', 'NON_QUALIFYING')}  "
            f"(QUALIFIES ✅)",
            f"  Window:         day {best.get('window_days')} "
            f"(return {best.get('return_date', NA)})",
            f"  Round-trip:     {_money(best.get('round_trip_total_usd'))}  "
            f"· {_savings(best)}",
            f"  Airline:        {best.get('airline') or NA}  "
            f"[{best.get('route_type', NA)}]  ·  "
            f"Duration {_dur(best.get('duration_minutes'))}",
            f"  Booking link:   {best.get('booking_url') or NA}",
        ])
    else:
        lines.append("Best combo:       none — no round trip has both legs ≥ YELLOW")
    lines.append("")
    return lines


def _reason(opt: dict, payload: dict, rank_idx: int) -> str:
    median = payload.get("median_total_usd")
    total = opt.get("round_trip_total_usd")
    bits = []
    if rank_idx == 1:
        bits.append(f"cheapest total of {payload.get('window_count', '?')} windows")
    if isinstance(median, (int, float)) and isinstance(total, (int, float)) and median:
        pct = (median - total) / median * 100.0
        if pct >= 0.5:
            bits.append(f"{pct:.0f}% below median")
    if opt.get("stops", 0) <= 0:
        bits.append("direct return")
    return "; ".join(bits) or "ranked by total trip cost"


def _render_option(idx: int, opt: dict, payload: dict, tag: str) -> list[str]:
    dest = payload.get("destination")
    origin = payload.get("origin")
    return [
        f"#{idx}{tag}",
        f"Return day:     {opt.get('window_days')}   ·   "
        f"Return date: {_date(opt.get('return_date') + 'T00:00:00') if opt.get('return_date') else NA}",
        f"Route:          {_airport(dest)} → {_airport(origin)}   "
        f"[{opt.get('route_type', NA)}]",
        f"Departure:      {_time(opt.get('depart_iso'))}      "
        f"Arrival: {_time(opt.get('arrive_iso'))}      "
        f"Duration: {_dur(opt.get('duration_minutes'))}",
        f"Airline:        {opt.get('airline') or NA}",
        f"Flight number:  {_flight_numbers(opt.get('flight_numbers'))}",
        f"Connection:     {_connection(opt)}      "
        f"Layover: {'none' if opt.get('stops', 0) <= 0 else NA}",
        f"Return price:   {_money(opt.get('return_price_usd'))}        "
        f"Total trip: {_money(opt.get('round_trip_total_usd'))}",
        f"Savings/typical:{_savings(opt)}",
        f"Outbound color: {_dot(opt.get('outbound_color')) or NA}",
        f"Return color:   {_dot(opt.get('color')) or NA}",
        f"Combo:          {_combo(opt)}",
        f"Booking link:   {opt.get('booking_url') or NA}",
        f"Reason ranked:  {_reason(opt, payload, idx)}",
    ]


def _verdict_route(opt: Optional[dict]) -> str:
    if not opt:
        return NA
    air = opt.get("airline") or "?"
    return f"{air}, {opt.get('route_type', '?')}"


def _render_verdict(payload: dict, ranking: dict) -> list[str]:
    cheapest = ranking.get("cheapest_total")
    fastest = ranking.get("best_travel_time")
    direct = ranking.get("best_direct")
    avoid = ranking.get("avoid") or []
    prov = payload.get("provenance", "placeholder")

    best_day = cheapest.get("window_days") if cheapest else None
    best_date = _date(cheapest["return_date"] + "T00:00:00") if cheapest and cheapest.get("return_date") else NA
    best_total = _money(cheapest.get("round_trip_total_usd")) if cheapest else NA

    avoid_line = NA
    if avoid:
        a = avoid[0]
        avoid_line = (
            f"day {a.get('window_days')} — {_money(a.get('round_trip_total_usd'))}, "
            f"{a.get('route_type', '?')}"
        )

    conf = (
        "HIGH (price/airline/times/duration live); flight#/connection/layover "
        "unavailable from source"
        if prov == "live" else
        "PLACEHOLDER data — for layout review only, not bookable"
    )

    return [
        "FINAL VERDICT:",
        f"Best return day:      {best_day if best_day is not None else NA} ({best_date})",
        f"Best total price:     {best_total} round-trip",
        f"Best airline/routing: {_verdict_route(direct)}",
        f"Best value:           {_verdict_route(cheapest)} at {best_total}",
        f"Fastest return:       {_dur(fastest.get('duration_minutes')) if fastest else NA}"
        f" ({_verdict_route(fastest)})" if fastest else f"Fastest return:       {NA}",
        f"Avoid:                {avoid_line}",
        f"Confidence:           {conf}",
    ]
