"""Which snapshot of the gateway's SDK contract this build was cut from (``contract/contract.json``).

Routes, enums and models are generated from the gateway's OpenAPI document into
:mod:`oblodai.generated`; this package keeps the snapshot's identity and the route types.
"""

from __future__ import annotations

from .types import RouteAuth, RouteSpec
from .version import CONTRACT_CORE_COMMIT, CONTRACT_EXPORTED_AT, CONTRACT_HASH

__all__ = [
    "CONTRACT_CORE_COMMIT",
    "CONTRACT_EXPORTED_AT",
    "CONTRACT_HASH",
    "RouteAuth",
    "RouteSpec",
]
