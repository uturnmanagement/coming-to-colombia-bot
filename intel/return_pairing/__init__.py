"""Return-pairing intel — pure logic for matching outbound Colombia
deals with possible return-leg windows.

Exports:
    RETURN_WINDOWS_DAYS    canonical window list (4, 7, 10, 14, 21, 30, 42, 50)
    ReturnOption           one return-leg candidate
    PairingEstimate        an outbound priced with each return window
    generate_windows       date arithmetic
    estimate_pairing       pure pairing under a fetcher protocol
"""
from .windows import (
    RETURN_WINDOWS_DAYS,
    ReturnWindowMode,
    generate_windows,
    parse_fixed_list,
    range_windows,
    resolve_return_windows,
)
from .pairing import (
    PairingEstimate,
    ReturnLegFetcher,
    ReturnOption,
    estimate_pairing,
)

__all__ = [
    "RETURN_WINDOWS_DAYS",
    "ReturnWindowMode",
    "ReturnLegFetcher",
    "ReturnOption",
    "PairingEstimate",
    "generate_windows",
    "parse_fixed_list",
    "range_windows",
    "resolve_return_windows",
    "estimate_pairing",
]
