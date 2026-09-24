"""Shared plumbing for the asynchronous resource namespaces (the twin of ``resources/base.py``)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Mapping, Optional, TypeVar

from ..contract.routes import ROUTES
from ..core.atransport import AsyncTransport
from ..core.options import RequestOptions
from ..core.pagination import AsyncPage, PageResult
from ..core.poller import AsyncJob, JobPlan, Parsers, job_id, plan_job, poll_options
from ..core.raw import RawAPIResponse
from ..core.request import Query
from ..core.route import RouteSpec
from ..resources.base import (
    FileResult,
    PathParams,
    Resource,
    _to_page,
    call_options,
    file_result,
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
    #: Routes by ``operationId`` for follow-up calls (polling a long-running operation);
    #: ``None`` means the generated route table.
    _operations: Optional[Mapping[str, RouteSpec]] = None
    #: Parsers of poll answers by model name; ``None`` means the generated models.
    _models: Optional[Parsers] = None

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
        """Call an envelope route; return its ``result``, or ``parse(result)`` when given.

        A long-running operation (:mod:`oblodai.lro`) returns an
        :class:`~oblodai.core.poller.AsyncJob` around that value.
        """
        opts = call_options(options, body, path_params, query)
        parser: Optional[Callable[[Any], Any]] = parse
        plan = plan_job(route, self._operations, self._models)
        if plan is not None:
            parser = self._job_parser(plan, options, parse)
        if self._raw_response:
            return RawAPIResponse(route, await self._transport.call_raw(route, opts), parser)
        result = await self._transport.call(route, opts)
        return parser(result) if parser is not None else result

    def _job_parser(
        self, plan: JobPlan, options: RequestOptions, parse: Optional[Callable[[Any], Any]]
    ) -> Callable[[Any], AsyncJob[Any]]:
        transport = self._transport
        follow = poll_options(options)

        def build(result: Any) -> AsyncJob[Any]:
            id = job_id(plan, result)

            async def poll() -> Any:
                body = {plan.id_field: id}
                answer = await transport.call(plan.poll_route, call_options(follow, body))
                return plan.parse(answer) if plan.parse is not None else answer

            def download(route: RouteSpec) -> Callable[[], Awaitable[FileResult]]:
                async def fetch() -> FileResult:
                    query = {plan.id_field: id}
                    raw = await transport.call_raw(route, call_options(follow, query=query))
                    return file_result(raw)

                return fetch

            return AsyncJob(
                id,
                parse(result) if parse is not None else result,
                poll,
                download(plan.download_route) if plan.download_route is not None else None,
            )

        return build

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
        return file_result(raw)
