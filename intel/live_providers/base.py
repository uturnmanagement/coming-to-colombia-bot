"""Live-provider foundation — gating + uniform failure handling.

This is the Layer 7A substrate for *live* airfare / lodging data. It is
deliberately decoupled from any real network library: the actual request
is delegated to an injectable ``transport`` callable (see
``transport.py``). That keeps the whole foundation hermetically testable
— mock mode, missing-key mode, and fake-response mode all run with no
external API.

The contract every concrete provider inherits from ``LiveProvider``:

    - Never raises out of ``fetch(...)``. Every outcome — including a
      missing key, a disabled gate, a timeout, a transport error, an
      empty payload, or a malformed payload — is reported as a typed
      ``LiveResult`` with a ``LiveProviderStatus``.
    - The wire stays closed unless ``enable_live=True`` AND an
      ``api_key`` is present. This mirrors the Layer 4 STUB stance.

Layer 7A ships NO live Telegram path and NO real HTTP transport wired by
default; producing data objects is the entire job of this package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class LiveProviderStatus(str, Enum):
    """Coarse outcome of a single live-provider fetch."""
    OK = "ok"              # usable data returned
    EMPTY = "empty"        # reached the source; nothing for this query
    MALFORMED = "malformed"  # payload shape/type not as expected
    TIMEOUT = "timeout"    # transport timed out
    ERROR = "error"        # transport or unexpected failure
    NO_KEY = "no_key"      # enable_live=True but no api_key configured
    DISABLED = "disabled"  # enable_live=False (the default, safe posture)


class ProviderTimeout(Exception):
    """Raised by a transport when a request exceeds its time budget."""


class ProviderTransportError(Exception):
    """Raised by a transport for any non-timeout failure (incl. the
    default 'not wired' transport used in Layer 7A)."""


@dataclass(frozen=True)
class LiveResult:
    """Typed outcome of ``LiveProvider.fetch``.

    ``data`` is a tuple of normalized records on OK, otherwise empty.
    ``reason`` is a human-readable explanation for any non-OK status.
    """
    status: LiveProviderStatus
    data: tuple = ()
    reason: str = ""
    source: str = ""
    raw_count: int = 0

    @property
    def is_usable(self) -> bool:
        return self.status is LiveProviderStatus.OK and bool(self.data)


@dataclass(frozen=True)
class LiveProviderConfig:
    """Runtime gates for a live provider."""
    provider_name: str = "mock"
    enable_live: bool = False
    api_key: str = ""
    timeout_seconds: float = 8.0


@dataclass
class LiveProvider:
    """Base class: gating + uniform failure handling.

    Subclasses implement ``_build_request`` (turn a query into transport
    kwargs) and ``_parse`` (turn a raw payload into a tuple of normalized
    records, raising on malformed input).
    """
    config: LiveProviderConfig = field(default_factory=LiveProviderConfig)
    # The transport is the only seam that could ever touch the network.
    # It defaults to a closed wire (see transport.not_wired_transport),
    # so a provider is inert until a real transport is injected.
    transport: Optional[Callable[..., Any]] = None
    name: str = "live"

    def __post_init__(self) -> None:
        if self.transport is None:
            # Imported lazily to avoid a circular import at module load.
            from .transport import not_wired_transport
            self.transport = not_wired_transport

    # --- public API -------------------------------------------------------

    def fetch(self, **query) -> LiveResult:
        """Run one query end-to-end and report a typed LiveResult.

        Failure ladder (each maps to a distinct status):
          DISABLED  -> enable_live is False
          NO_KEY    -> enabled but no api_key
          TIMEOUT   -> transport raised ProviderTimeout
          ERROR     -> transport raised anything else
          EMPTY     -> transport/parse produced no records
          MALFORMED -> parse raised on shape/type
          OK        -> usable records
        """
        if not self.config.enable_live:
            return self._result(
                LiveProviderStatus.DISABLED,
                reason="live disabled (set enable_live=True to activate)",
            )
        if not self.config.api_key:
            return self._result(
                LiveProviderStatus.NO_KEY,
                reason="enable_live=True but no api_key configured",
            )

        try:
            request_kwargs = self._build_request(**query)
            raw = self.transport(
                timeout=self.config.timeout_seconds, **request_kwargs
            )
        except ProviderTimeout as exc:
            return self._result(LiveProviderStatus.TIMEOUT, reason=str(exc) or "timeout")
        except Exception as exc:  # noqa: BLE001 — transport must not escape
            return self._result(
                LiveProviderStatus.ERROR,
                reason=f"{type(exc).__name__}: {exc}",
            )

        if raw is None:
            return self._result(LiveProviderStatus.EMPTY, reason="no payload")

        try:
            records = tuple(self._parse(raw))
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            return self._result(
                LiveProviderStatus.MALFORMED,
                reason=f"{type(exc).__name__}: {exc}",
            )

        if not records:
            return self._result(LiveProviderStatus.EMPTY, reason="no records in payload")

        return LiveResult(
            status=LiveProviderStatus.OK,
            data=records,
            source=self.name,
            raw_count=len(records),
        )

    # --- subclass hooks ---------------------------------------------------

    def _build_request(self, **query) -> dict:
        """Translate a query into transport kwargs. Default: pass through."""
        return dict(query)

    def _parse(self, raw: Any) -> tuple:  # pragma: no cover - overridden
        raise NotImplementedError

    # --- internals --------------------------------------------------------

    def _result(self, status: LiveProviderStatus, *, reason: str) -> LiveResult:
        return LiveResult(status=status, reason=reason, source=self.name)
