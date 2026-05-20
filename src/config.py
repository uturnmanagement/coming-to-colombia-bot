"""Environment configuration + region-pack wiring.

Secrets and operational cadence come from the environment (.env). All
geography and deal thresholds come from the active region pack — which
`load_config()` loads and activates. `load_config()` never raises; call
`Config.validate()` to surface problems before starting the bot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import region as region_mod
from .region import RegionPack

try:  # python-dotenv is optional at import time (e.g. during tests).
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    try:
        return int(float(_get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # --- Telegram ---
    telegram_bot_token: str
    telegram_chat_id: str
    # --- Flight data source ---
    flight_api_provider: str
    flight_api_key: str
    flight_api_secret: str
    rapidapi_key: str
    rapidapi_host: str
    # --- Region selection ---
    region_pack: str
    # --- Operational ---
    timezone: str
    red_heartbeat_minutes: int
    red_heartbeat_duration_hours: float
    yellow_recheck_minutes: int
    green_summary_hour: int
    # --- Loaded region pack (set by load_config) ---
    region: RegionPack | None = None
    region_error: str = ""

    # Deal thresholds delegate to the active region pack so each market
    # (luxury, backpacker, ...) tunes them independently.
    @property
    def positioning_min_savings_usd(self) -> float:
        return self.region.min_positioning_savings_usd

    @property
    def red_min_savings_usd(self) -> float:
        return self.region.red_min_savings_usd

    @property
    def yellow_min_savings_usd(self) -> float:
        return self.region.yellow_min_savings_usd

    @property
    def max_acceptable_layover_hours(self) -> float:
        return self.region.max_layover_hours

    @property
    def scan_days_ahead(self) -> int:
        return self.region.scan_days_ahead

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.telegram_bot_token:
            problems.append("TELEGRAM_BOT_TOKEN is not set.")
        if not self.telegram_chat_id:
            problems.append(
                "TELEGRAM_CHAT_ID is not set (run /chatid in Telegram to find it)."
            )
        if self.region is None:
            problems.append(
                f"Region pack '{self.region_pack}' failed to load: "
                f"{self.region_error}"
            )
        if self.flight_api_provider == "amadeus":
            if not self.flight_api_key:
                problems.append(
                    "FLIGHT_API_PROVIDER is 'amadeus' but FLIGHT_API_KEY is empty."
                )
            if not self.flight_api_secret:
                problems.append(
                    "FLIGHT_API_PROVIDER is 'amadeus' but FLIGHT_API_SECRET is empty."
                )
        if not 0 <= self.green_summary_hour <= 23:
            problems.append("GREEN_SUMMARY_HOUR must be between 0 and 23.")
        return problems

    @property
    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def summary(self) -> str:
        region_name = self.region.name if self.region else "?"
        return (
            f"region={region_name} pack={self.region_pack} "
            f"provider={self.flight_api_provider} tz={self.timezone} "
            f"recheck={self.yellow_recheck_minutes}m "
            f"heartbeat={self.red_heartbeat_minutes}m/"
            f"{self.red_heartbeat_duration_hours}h"
        )


def load_config() -> Config:
    """Load environment config and the active region pack (never raises)."""
    load_dotenv()
    cfg = Config(
        telegram_bot_token=_get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get("TELEGRAM_CHAT_ID"),
        flight_api_provider=_get("FLIGHT_API_PROVIDER", "placeholder").lower(),
        flight_api_key=_get("FLIGHT_API_KEY"),
        flight_api_secret=_get("FLIGHT_API_SECRET"),
        rapidapi_key=_get("RAPIDAPI_KEY"),
        rapidapi_host=_get(
            "RAPIDAPI_HOST", "skyscanner-flights-travel-api.p.rapidapi.com"
        ),
        region_pack=_get("REGION_PACK", "colombia"),
        timezone=_get("TIMEZONE", "America/Bogota"),
        red_heartbeat_minutes=_get_int("RED_HEARTBEAT_MINUTES", 5),
        red_heartbeat_duration_hours=_get_float("RED_HEARTBEAT_DURATION_HOURS", 2),
        yellow_recheck_minutes=_get_int("YELLOW_RECHECK_MINUTES", 45),
        green_summary_hour=_get_int("GREEN_SUMMARY_HOUR", 9),
    )
    try:
        pack = region_mod.load_region_pack(cfg.region_pack)
        cfg.region = pack
        region_mod.set_active(pack)
    except Exception as exc:  # noqa: BLE001 - surfaced via validate()
        cfg.region_error = str(exc)
    return cfg
