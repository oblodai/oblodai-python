"""Shared plumbing for the asynchronous resource namespaces (the twin of ``resources/base.py``)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping, Optional, TypeVar

from ..core.atransport import AsyncTransport
from ..core.engine import unwrap_result
from ..core.options import RequestOptions
from ..core.pagination import AsyncPage, PageResult
from ..core.poller import AsyncJob, JobPlan, Parsers, job_id, plan_job, poll_options
from ..core.raw import RawAPIResponse
from ..core.request import Query
from ..core.route import RouteSpec
from ..core.steps import RawResponse
from ..resources.base import (
    FileResult,
    PagedRequest,
    PathParams,
    call_options,
    file_result,
    plan_paged,
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
        """The async twin of :meth:`oblodai.resources.base.Resource._request`: an envelope route
        returns its ``result`` (or ``parse(result)``; an :class:`~oblodai.core.poller.AsyncJob`
        for a long-running operation), a paged list a lazy :class:`AsyncPage`, a ``bare`` route a
        :class:`FileResult`; each as a :class:`RawAPIResponse` through ``with_raw_response``.
        """
        if route.bare:
            opts = call_options(options, body, path_params, query)
            raw = await self._transport.call_raw(route, opts)
            if self._raw_response:
                return RawAPIResponse(route, raw, decode=file_result)
            return file_result(raw)
        if route.list_kind == "paged":
            return await self._paged(plan_paged(route, body, query, options, path_params, parse))
        opts = call_options(options, body, path_params, query)
        parser: Optional[Callable[[Any], Any]] = parse
        plan = plan_job(route, self._operations, self._models)
        if plan is not None:
            parser = self._job_parser(plan, options, parse)
        if self._raw_response:
            return RawAPIResponse(route, await self._transport.call_raw(route, opts), parser)
        result = await self._transport.call(route, opts)
        return parser(result) if parser is not None else result

    async def _paged(self, plan: PagedRequest) -> Any:
        transport = self._transport

        async def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            call = plan.call_options(page_limit, page_offset)
            return plan.page(await transport.call(plan.route, call))

        if not self._raw_response:
            return AsyncPage(fetch, plan.limit, plan.offset)
        raw = await transport.call_raw(plan.route, plan.first_call_options())

        def decode(response: RawResponse) -> AsyncPage[Any]:
            page = plan.page(unwrap_result(plan.route, response))
            return AsyncPage(fetch, plan.limit, plan.offset, first=page)

        return RawAPIResponse(plan.route, raw, decode=decode)

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
