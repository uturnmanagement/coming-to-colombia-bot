"""Transports — the only seam that could ever touch the network.

Layer 7A ships exactly two transports, neither of which makes a real
external call:

  - ``not_wired_transport`` — the default. Always raises
    ``ProviderTransportError`` so a configured-but-unwired provider
    reports ERROR instead of silently doing nothing. This preserves the
    Layer 4 STUB-safety philosophy: even with enable_live + a key, no
    real request happens until a transport is deliberately supplied.

  - ``InjectableTransport`` — for local testing ("fake provider response
    mode"). Returns a preset payload, or raises a preset exception so
    timeout / error / malformed paths can be exercised offline.

A real ``requests``-backed transport is intentionally NOT included here;
wiring live HTTP is a later-layer concern. Keeping it out guarantees the
foundation cannot reach the internet by accident.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .base import ProviderTransportError


def not_wired_transport(*, timeout: float = 8.0, **_request) -> Any:
    """Default transport: the wire is closed in Layer 7A."""
    raise ProviderTransportError(
        "live transport not implemented in Layer 7A "
        "(inject a transport to activate)"
    )


@dataclass
class InjectableTransport:
    """Deterministic transport for tests and mock providers.

    Construct with exactly one of:
      - ``response`` — returned verbatim from every call, OR
      - ``error``    — an exception instance raised on every call.

    ``last_call`` captures the kwargs of the most recent invocation so a
    test can assert the request was built correctly.
    """
    response: Any = None
    error: Optional[BaseException] = None
    last_call: Optional[dict] = None

    def __call__(self, *, timeout: float = 8.0, **request) -> Any:
        self.last_call = {"timeout": timeout, **request}
        if self.error is not None:
            raise self.error
        return self.response
