"""Types describing the route registry (``contract/routes.py``).

The registry itself is produced by ``scripts/codegen.py`` from ``contract/contract.json``, which is
exported from the core's own conformance table - so every route the SDK can call is one the core
declares, with the same auth gate and idempotency wrapper. The types live in the runtime
(:mod:`oblodai.core.route`); this module re-exports them for existing imports.
"""

from __future__ import annotations

from ..core.route import HttpMethod, ListKind, RouteAuth, RouteSpec

__all__ = ["HttpMethod", "ListKind", "RouteAuth", "RouteSpec"]
