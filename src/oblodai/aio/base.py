"""Shared plumbing for the asynchronous resource namespaces (the twin of ``resources/base.py``)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from ..contract.routes import ROUTES
from ..core.atransport import AsyncTransport
from ..core.pagination import AsyncPage, PageResult
from ..core.request import Query
from ..resources.base import FileResult, PathParams, Resource, _to_page, filename_from

__all__ = ["AsyncResource", "FileResult"]


class AsyncResource:
    """Base of every namespace on :class:`~oblodai.AsyncOblodai`.

    The trailing keyword arguments are identical to the synchronous client's
    (:class:`oblodai.resources.base.Resource`): ``idempotency_key``, ``timeout_ms``,
    ``deadline_ms``, ``prefer_payout_key``.
    """

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    async def _call(
        self,
        key: str,
        body: Any = None,
        *,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        **options: Any,
    ) -> Any:
        """Call an envelope route and return its ``result``."""
        return await self._transport.call(
            ROUTES[key], Resource._options(body, path_params, query, options)
        )

    async def _plain_list(self, key: str, body: Any = None, **options: Any) -> List[Any]:
        """Call a plain list route (``{items}`` without ``paginate``)."""
        from ..core.envelope import as_plain_list

        result = await self._transport.call(
            ROUTES[key], Resource._options(body, None, None, options)
        )
        return as_plain_list(result)

    def _page(
        self,
        key: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        path_params: Optional[PathParams] = None,
        via_query: bool = False,
        **options: Any,
    ) -> AsyncPage[Any]:
        """Call a paged list route (``{items, paginate}``); returns a lazy :class:`AsyncPage`."""
        rest: Dict[str, Any] = dict(params or {})
        # `history({"limit": 50})` and `history(limit=50)` are both accepted.
        for shortcut in ("limit", "offset"):
            if shortcut in options:
                rest[shortcut] = options.pop(shortcut)
        limit = rest.pop("limit", None)
        offset = rest.pop("offset", None)
        # One key per page would be wrong on both sides: the core would replay page 1 forever.
        page_options = {k: v for k, v in options.items() if k != "idempotency_key"}
        route = ROUTES[key]
        use_query = route.method == "GET" or via_query

        async def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            merged = {**rest, "limit": page_limit, "offset": page_offset}
            call_options = Resource._options(
                None if use_query else merged,
                path_params,
                merged if use_query else None,
                page_options,
            )
            return _to_page(await self._transport.call(route, call_options))

        return AsyncPage(fetch, limit, offset)

    async def _file(
        self,
        key: str,
        *,
        body: Any = None,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        **options: Any,
    ) -> FileResult:
        """Call a ``bare`` route and return its bytes."""
        raw = await self._transport.call_raw(
            ROUTES[key], Resource._options(body, path_params, query, options)
        )
        return FileResult(
            content=raw.body,
            content_type=raw.content_type or "application/octet-stream",
            filename=filename_from(raw.header("content-disposition")),
        )
