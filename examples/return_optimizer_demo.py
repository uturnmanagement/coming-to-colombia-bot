"""DRY_RUN demo — OAK STREET Delta return optimizer.

Hermetic: uses the deterministic placeholder offer-fetcher, so it renders
the full report layout offline with NO live API calls and NO Telegram.
Every row is tagged as placeholder data — it is NOT real airline info.

Run:
    python examples/return_optimizer_demo.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.delta import Delta, make_placeholder_offer_fetcher, render_delta_report
from agents.delta.specialist import sampled_return_days
from agents.oakstreet import AlertEvent
from src import region


def main() -> None:
    # The placeholder fetcher prices against the active region pack — load
    # the Colombia pack so the demo runs hermetically (no .env / API needed).
    region.set_active(region.load_region_pack("colombia"))

    outbound_depart = datetime(2026, 6, 20, 7, 45)
    event = AlertEvent(
        deal_id="DEMO-MDE",
        color="green",
        price_usd=312.0,
        route_signature="BWI->MDE",
        departure_at=outbound_depart,
        observed_at=datetime(2026, 5, 31, 9, 0),
        summary="BWI->MDE $312",
    )
    # Sample the 4–60 day window the way the live path would, but price it
    # with the offline placeholder so this stays hermetic.
    windows = sampled_return_days(tuple(range(4, 61)))
    delta = Delta(fetcher=make_placeholder_offer_fetcher(), windows=windows)
    report = delta.analyze(event, origin="BWI")
    print(render_delta_report(report.payload))


if __name__ == "__main__":
    main()
