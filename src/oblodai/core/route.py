"""What one route of the API is, and how to follow a long-running one, as the runtime needs it.

Runtime, not contract: the generated tables (:mod:`oblodai.generated.routes`,
:mod:`oblodai.generated.lro`) and the older contract mirror describe their routes with these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

__all__ = ["HttpMethod", "ListKind", "Poll", "RouteAuth", "RouteSpec"]

HttpMethod = Literal["GET", "POST"]

#: Which credential the core's gate expects. Mirrors api_conformance_test.go constants:
#: ``public`` - unsigned; ``key`` - signed with the merchant's one API key; ``onboard`` -
#: ``X-Admin-Token``. A merchant has a single key, so there is no kind to choose between.
RouteAuth = Literal["public", "key", "onboard"]

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
    #: The OpenAPI ``operationId``; empty for routes of the older contract mirror.
    operation_id: str = ""

    @property
    def key(self) -> str:
        """``"POST /v1/payment"`` - the method and path of this route."""
        return f"{self.method} {self.path}"


@dataclass(frozen=True)
class Poll:
    """How to follow one kind of job (the contract's ``x-sdk-poll``)."""

    #: The job's id in the create answer; sent under the same name to the poll (and download).
    id_field: str
    #: The model the poll answer parses to (in the generated models); empty - left unparsed.
    model: str
    #: The field of the poll answer that carries the job's status.
    status_field: str
    #: Statuses after which the job no longer changes.
    terminal: Tuple[str, ...]
    #: The ``operationId`` that returns the finished job's file, if the job makes one.
    download: Optional[str] = None
