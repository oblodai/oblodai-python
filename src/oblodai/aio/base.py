"""Shared plumbing for the asynchronous resource namespaces (the twin of ``resources/base.py``)."""

from __future__ import annotations

from typing import Any, Callable, List, Mapping, Optional, TypeVar

from ..contract.routes import ROUTES
from ..core.atransport import AsyncTransport
from ..core.options import RequestOptions
from ..core.pagination import AsyncPage, PageResult
from ..core.raw import RawAPIResponse
from ..core.request import Query
from ..core.route import RouteSpec
from ..resources.base import (
    FileResult,
    PathParams,
    Resource,
    _to_page,
    call_options,
    filename_from,
    plan_page,
    raw_copy,
)

__all__ = ["AsyncResource", "FileResult"]

T = TypeVar("T")


class AsyncResource:
    """Base of every namespace on :class:`~oblodai.AsyncOblodai`.

    The trailing keyword arguments are identical to the synchronous client's
    (:class:`oblodai.resources.base.Resource`): the fields of :class:`~oblodai.RequestOptions`.
    """

    #: Set on the copy :attr:`with_raw_response` hands out, never on the namespace itself.
    _raw_response = False

    def __init__(self, transport: AsyncTransport) -> None:
        self._transport = transport

    @property
    def with_raw_response(self) -> Any:
        """The same methods, returning :class:`~oblodai.RawAPIResponse` (status, headers,
        ``request_id``, ``parse()``) instead of the parsed result."""
        return raw_copy(self)

    async def _request(
        self,
        route: RouteSpec,
        body: Any,
        options: RequestOptions,
        *,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        parse: Optional[Callable[[Any], T]] = None,
    ) -> Any:
        """Call an envelope route; return its ``result``, or ``parse(result)`` when given."""
        opts = call_options(options, body, path_params, query)
        if self._raw_response:
            return RawAPIResponse(route, await self._transport.call_raw(route, opts), parse)
        result = await self._transport.call(route, opts)
        return parse(result) if parse is not None else result

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
        plan = plan_page(key, params, via_query, options)

        async def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            call_options = plan.call_options(page_limit, page_offset, path_params)
            return _to_page(await self._transport.call(plan.route, call_options))

        return AsyncPage(fetch, plan.limit, plan.offset)

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
