"""Which contract this build was generated from, and the route types.

Routes, enums, models and the contract's identity (``info.version`` and the sha256 of
``openapi.json``) are generated from the gateway's OpenAPI document into :mod:`oblodai.generated`;
this package re-exports the identity.
"""

from __future__ import annotations

from .types import RouteAuth, RouteSpec
from .version import CONTRACT_HASH, CONTRACT_VERSION

__all__ = [
    "CONTRACT_HASH",
    "CONTRACT_VERSION",
    "RouteAuth",
    "RouteSpec",
]
