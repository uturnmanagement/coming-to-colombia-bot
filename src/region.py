"""Region pack model and loader — the heart of the global framework.

A region pack (configs/<name>.yaml) defines an entire airfare market:
origin airport, destinations, gateway cities, positioning rules, deal
thresholds, and per-destination arrival-time rules. All geography is
data — nothing is hardcoded — so the same code serves USA->Colombia,
NYC->Europe, LAX->Japan, a backpacker pack, a luxury pack, and so on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:  # PyYAML is required to load region packs.
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

DEAL_COLOR_EMOJI = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


@dataclass
class ArrivalRule:
    """Per-destination arrival-time preference (generalizes the MDE rule)."""

    preferred_start: int = 10
    preferred_end: int = 15
    late_night_start: int = 21


@dataclass
class Destination:
    code: str
    city: str
    typical_price_usd: float
    arrival_rule: ArrivalRule | None = None


@dataclass
class RegionPack:
    """A fully-described airfare market loaded from a region pack YAML."""

    name: str
    slug: str
    description: str
    origin: str
    origin_label: str
    destinations: dict[str, Destination]
    gateways: dict[str, str]
    preferred_gateways: dict[str, list[str]]
    min_positioning_savings_usd: float
    max_layover_hours: float
    red_min_savings_usd: float
    yellow_min_savings_usd: float
    scan_days_ahead: int
    preferred_airlines: list[str] = field(default_factory=list)
    budget_label: str = "standard"

    # --- helpers ---
    def destination_codes(self) -> list[str]:
        return list(self.destinations)

    def is_destination(self, code: str) -> bool:
        return (code or "").upper() in self.destinations

    def is_gateway(self, code: str) -> bool:
        return (code or "").upper() in self.gateways

    def typical_price(self, code: str) -> float:
        dest = self.destinations.get((code or "").upper())
        return dest.typical_price_usd if dest else 400.0

    def city_name(self, code: str) -> str:
        code = (code or "").upper()
        if code == self.origin:
            return self.origin_label
        if code in self.destinations:
            return self.destinations[code].city
        if code in self.gateways:
            return self.gateways[code]
        return code

    def city_label(self, code: str) -> str:
        code = (code or "").upper()
        name = self.city_name(code)
        return f"{name} ({code})" if name != code else code

    def gateways_for(self, destination: str) -> list[str]:
        return self.preferred_gateways.get(
            (destination or "").upper(), list(self.gateways)
        )

    def arrival_rule(self, destination: str) -> ArrivalRule | None:
        dest = self.destinations.get((destination or "").upper())
        return dest.arrival_rule if dest else None


# --- active region (one bot process serves one region pack) ----------------

_ACTIVE: RegionPack | None = None


def set_active(pack: RegionPack) -> None:
    global _ACTIVE
    _ACTIVE = pack


def active() -> RegionPack:
    if _ACTIVE is None:
        raise RuntimeError("No active region pack — call region.set_active() first.")
    return _ACTIVE


def origin() -> str:
    return active().origin


def destination_codes() -> list[str]:
    return active().destination_codes()


def city_label(code: str) -> str:
    return active().city_label(code)


def typical_price(code: str) -> float:
    return active().typical_price(code)


def gateways_for(destination: str) -> list[str]:
    return active().gateways_for(destination)


def is_destination(code: str) -> bool:
    return active().is_destination(code)


# --- loader ----------------------------------------------------------------

def load_region_pack(slug_or_path: str) -> RegionPack:
    """Load a region pack by slug (configs/<slug>.yaml) or explicit path."""
    if yaml is None:
        raise RuntimeError("PyYAML is required — pip install -r requirements.txt")
    path = Path(slug_or_path)
    if not path.suffix:
        path = CONFIGS_DIR / f"{slug_or_path}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Region pack not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _build_pack(raw, path.stem)


def _build_pack(raw: dict, fallback_slug: str) -> RegionPack:
    region = raw.get("region", {}) or {}
    origin_blk = raw.get("origin", {}) or {}
    positioning = raw.get("positioning", {}) or {}
    thresholds = raw.get("thresholds", {}) or {}
    scan = raw.get("scan", {}) or {}

    destinations: dict[str, Destination] = {}
    for code, dest in (raw.get("destinations") or {}).items():
        code = str(code).upper()
        dest = dest or {}
        arrival = None
        rule = dest.get("arrival_rules")
        if rule:
            arrival = ArrivalRule(
                preferred_start=int(rule.get("preferred_start", 10)),
                preferred_end=int(rule.get("preferred_end", 15)),
                late_night_start=int(rule.get("late_night_start", 21)),
            )
        destinations[code] = Destination(
            code=code,
            city=str(dest.get("city", code)),
            typical_price_usd=float(dest.get("typical_price_usd", 400)),
            arrival_rule=arrival,
        )

    gateways = {
        str(k).upper(): str(v) for k, v in (raw.get("gateways") or {}).items()
    }
    preferred = {
        str(k).upper(): [str(g).upper() for g in (v or [])]
        for k, v in (positioning.get("preferred_gateways") or {}).items()
    }
    primary_origin = str(origin_blk.get("primary", "BWI")).upper()

    return RegionPack(
        name=str(region.get("name", fallback_slug.replace("_", " ").title())),
        slug=str(region.get("slug", fallback_slug)),
        description=str(region.get("description", "")),
        origin=primary_origin,
        origin_label=str(origin_blk.get("label", primary_origin)),
        destinations=destinations,
        gateways=gateways,
        preferred_gateways=preferred,
        min_positioning_savings_usd=float(positioning.get("min_savings_usd", 100)),
        max_layover_hours=float(positioning.get("max_layover_hours", 12)),
        red_min_savings_usd=float(thresholds.get("red_min_savings_usd", 150)),
        yellow_min_savings_usd=float(thresholds.get("yellow_min_savings_usd", 75)),
        scan_days_ahead=int(scan.get("days_ahead", 21)),
        preferred_airlines=[str(a) for a in (raw.get("preferred_airlines") or [])],
        budget_label=str(raw.get("budget_label", "standard")),
    )
