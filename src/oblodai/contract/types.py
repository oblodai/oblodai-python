"""Hand-written types describing the generated route registry (``contract/routes.py``).

The registry itself is produced by ``scripts/codegen.py`` from ``contract/contract.json``, which is
exported from the core's own conformance table - so every route the SDK can call is one the core
declares, with the same auth gate and idempotency wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

HttpMethod = Literal["GET", "POST"]

#: Which credential the core's gate expects. Mirrors api_conformance_test.go constants.
RouteAuth = Literal["public", "payment", "payout", "any", "onboard"]

ListKind = Literal["paged", "plain"]


@dataclass(frozen=True)
class RouteSpec:
    """One route of the merchant surface."""

    method: HttpMethod
    #: Path template; ``{name}`` segments are filled from ``path_params``.
    path: str
    auth: RouteAuth
    #: Wrapped in the core's ``withIdempotency``: a key is generated when the caller supplies none.
    idempotent: bool
    #: Read-only: a transport failure may be retried without risking a duplicate side effect.
    safe: bool
    #: Outside the JSON envelope (binary documents, health pages).
    bare: bool
    #: ``paged`` for ``{items, paginate}`` lists, ``plain`` for ``{items}`` lists.
    list_kind: Optional[ListKind] = None

    @property
    def key(self) -> str:
        """``"POST /v1/payment"`` - the key this route has in ``ROUTES``."""
        return f"{self.method} {self.path}"
