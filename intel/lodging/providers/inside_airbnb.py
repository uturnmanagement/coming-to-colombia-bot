"""Inside Airbnb ingestion interface.

Layer 4 ships Inside Airbnb as a **stub** with the live filesystem
ingestion path deliberately closed. The provider knows about
`local_path` (set via `INSIDE_AIRBNB_LOCAL_PATH`) so a future layer
can drop a CSV/Parquet reader in without changing the interface — but
no file is read in Layer 4.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .interface import LodgingProvider, ProviderResult, ProviderStatus


@dataclass
class InsideAirbnbProvider(LodgingProvider):
    name: str = "inside_airbnb"
    local_path: Optional[Path] = None
    enable_live: bool = False  # explicit opt-in; default off in Layer 4

    def fetch(
        self,
        *,
        city: str,
        neighborhood: Optional[str] = None,
        beds: Optional[int] = None,
        lookback_days: int = 90,
        now: Optional[datetime] = None,
    ) -> ProviderResult:
        if not self.enable_live or self.local_path is None:
            return ProviderResult(
                status=ProviderStatus.STUB,
                observations=(),
                reason=(
                    "Inside Airbnb local ingestion not enabled in Layer 4 "
                    "(set INSIDE_AIRBNB_LOCAL_PATH and enable_live=True to "
                    "activate)"
                ),
                source=self.name,
            )
        return ProviderResult(
            status=ProviderStatus.STUB,
            observations=(),
            reason="Inside Airbnb file ingestion not implemented in Layer 4",
            source=self.name,
        )
