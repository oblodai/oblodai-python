"""The contract snapshot as Python: routes, enums, request bodies, response models."""

from __future__ import annotations

from .routes import ROUTES, ROUTE_KEYS
from .types import RouteAuth, RouteSpec
from .version import CONTRACT_CORE_COMMIT, CONTRACT_EXPORTED_AT, CONTRACT_HASH

__all__ = [
    "CONTRACT_CORE_COMMIT",
    "CONTRACT_EXPORTED_AT",
    "CONTRACT_HASH",
    "ROUTES",
    "ROUTE_KEYS",
    "RouteAuth",
    "RouteSpec",
]
