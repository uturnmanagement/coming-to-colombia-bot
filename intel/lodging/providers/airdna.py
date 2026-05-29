"""AirDNA integration interface.

Layer 4 ships AirDNA as a **stub** — it owns the interface shape but
makes no HTTP calls. When an `api_key` is configured AND
`enable_live=True` AND a future `_fetch_live()` is implemented, this
will return real data; until then every `fetch(...)` returns
`ProviderResult(status=STUB, ...)` with a reason that explains why.

The stub stance is deliberate: we want every test, every CI run, and
every operator dry-run to go through this provider without surprise
network calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .interface import LodgingProvider, ProviderResult, ProviderStatus


@dataclass
class AirDnaProvider(LodgingProvider):
    name: str = "airdna"
    api_key: Optional[str] = None
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
        if not self.enable_live or not self.api_key:
            return ProviderResult(
                status=ProviderStatus.STUB,
                observations=(),
                reason=(
                    "AirDNA live fetch not enabled in Layer 4 "
                    "(set AIRDNA_API_KEY and enable_live=True to activate)"
                ),
                source=self.name,
            )
        # Live HTTP implementation is reserved for a later layer. Even
        # if you wire credentials, Layer 4 keeps the wire path closed.
        return ProviderResult(
            status=ProviderStatus.STUB,
            observations=(),
            reason="AirDNA live wire path not implemented in Layer 4",
            source=self.name,
        )
