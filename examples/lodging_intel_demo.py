"""Phase 6A lodging intelligence demo.

Run as a plain script (no pytest required):
    python examples/lodging_intel_demo.py

Prints the standalone Lodging Summary across all supported cities (the
15-city Colombia registry), then a single Delta-report appendix for one
destination (Medellín / MDE). Mock data only — no network.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lodging import render_all_cities, render_delta_lodging_appendix

# Fixed timestamp keeps the demo output reproducible.
NOW = datetime(2026, 6, 4, 9, 0, 0)


def main() -> None:
    print("=" * 64)
    print(render_all_cities(now=NOW))
    print("=" * 64)
    print("DELTA REPORT APPENDIX — destination MDE (Medellín):\n")
    print(render_delta_lodging_appendix("MDE", now=NOW))


if __name__ == "__main__":
    main()
