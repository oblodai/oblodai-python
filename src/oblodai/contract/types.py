"""Route types, re-exported from the runtime (:mod:`oblodai.core.route`) for existing imports.

The route table itself is generated from the gateway's OpenAPI document into
:mod:`oblodai.generated.routes`.
"""

from __future__ import annotations

from ..core.route import HttpMethod, ListKind, RouteAuth, RouteSpec

__all__ = ["HttpMethod", "ListKind", "RouteAuth", "RouteSpec"]
