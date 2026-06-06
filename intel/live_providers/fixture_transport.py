"""Fixture-backed lodging transport — Phase 6B (dark, recorded data).

This is the third — and intentionally *darkest* — transport in the
Layer 7A family:

  - ``not_wired_transport``  — closed wire (ERROR), the production stub.
  - ``InjectableTransport``  — preset payload/exception, for unit tests.
  - ``FixtureLodgingTransport`` (here) — serves **recorded, static**
    lodging payloads loaded from JSON files on disk.

The point of Phase 6B is to exercise the *entire* ``LiveLodgingProvider``
pipeline — gating → transport → parse → ``LodgingQuote`` normalization —
against realistic, recorded data, while contacting **no external API**.
The fixtures under ``fixtures/lodging/{CODE}.json`` are a frozen snapshot
(see each file's ``_meta``); they are NOT live pricing.

Safety properties this module guarantees:

  - **No network.** The only I/O is reading committed JSON files from the
    package's own ``fixtures`` directory. There is no socket, no
    ``requests`` import, nothing that can reach the internet.
  - **Gated like any live provider.** The provider is still built on
    ``LiveProvider``, so ``enable_live`` + ``api_key`` gating applies. A
    caller that does not opt in gets DISABLED/NO_KEY exactly as with the
    real adapter — the recorded data never leaks out by default.
  - **Deterministic.** Same city code always yields the same payload, so
    reports and tests are reproducible.

An unknown city returns ``None``, which the base maps to EMPTY (reached
the source, nothing for this query) — mirroring a real provider with no
listings for that city.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .base import LiveProviderConfig
from .lodging import LiveLodgingProvider

# Recorded fixtures live next to this module. Resolved once at import.
FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures" / "lodging"

# Sentinel api_key for the fixture provider. It is NOT a real secret — it
# only satisfies the base provider's NO_KEY gate so the recorded pipeline
# can run. Nothing is ever authenticated with it.
FIXTURE_API_KEY = "fixture"


@dataclass
class FixtureLodgingTransport:
    """Deterministic transport that replays recorded lodging snapshots.

    Reads ``{CODE}.json`` from ``fixtures_dir`` for the requested city,
    returning its raw payload (``{"listings": [...]}``) verbatim so the
    provider's ``_parse`` normalizes it just as it would a live payload.
    Unknown cities return ``None`` (-> EMPTY). Files are cached after
    first read; ``last_call`` records the most recent request for tests.
    """

    fixtures_dir: Path = FIXTURES_DIR
    last_call: Optional[dict] = None
    _cache: dict[str, Optional[dict]] = field(default_factory=dict)

    def available_cities(self) -> tuple[str, ...]:
        """City codes for which a recorded fixture exists (sorted)."""
        if not self.fixtures_dir.is_dir():
            return ()
        return tuple(sorted(p.stem.upper() for p in self.fixtures_dir.glob("*.json")))

    def _load(self, code: str) -> Optional[dict]:
        if code in self._cache:
            return self._cache[code]
        path = self.fixtures_dir / f"{code}.json"
        payload: Optional[dict]
        if not path.is_file():
            payload = None
        else:
            # Local file read only — no network is possible here.
            payload = json.loads(path.read_text(encoding="utf-8"))
        self._cache[code] = payload
        return payload

    def __call__(self, *, timeout: float = 8.0, params: dict = None,
                 api_key: str = "", **_) -> Any:
        params = params or {}
        code = str(params.get("city", "")).upper()
        self.last_call = {"timeout": timeout, "city": code, "api_key": api_key}
        if not code:
            return None
        return self._load(code)


def make_fixture_lodging_provider(
    *, fixtures_dir: Optional[Path] = None,
) -> LiveLodgingProvider:
    """Build a dark, fixture-backed live lodging provider.

    Enabled with a sentinel key so the gated pipeline runs end-to-end on
    recorded data — but every byte comes from committed JSON, never an
    API. Pass ``fixtures_dir`` to point at an alternate snapshot set
    (used by tests); defaults to the package's recorded fixtures.
    """
    transport = FixtureLodgingTransport(
        fixtures_dir=fixtures_dir or FIXTURES_DIR
    )
    return LiveLodgingProvider(
        config=LiveProviderConfig(
            provider_name="fixture",
            enable_live=True,
            api_key=FIXTURE_API_KEY,
        ),
        transport=transport,
        name="fixture_lodging",
    )
