"""Shared plumbing for the synchronous resource namespaces."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, TypeVar, Union
from urllib.parse import unquote

from ..contract.models.common import Paginate
from ..contract.routes import ROUTES
from ..core.engine import CallOptions, unwrap_result
from ..core.envelope import as_page, as_plain_list
from ..core.errors import ConfigError
from ..core.options import RequestOptions, options_from_kwargs
from ..core.pagination import DEFAULT_PAGE_LIMIT, Page, PageResult
from ..core.poller import Job, JobPlan, Parsers, job_id, plan_job, poll_options
from ..core.raw import RawAPIResponse
from ..core.request import Query
from ..core.route import RouteSpec
from ..core.steps import RawResponse
from ..core.transport import Transport

__all__ = [
    "FileResult",
    "PagePlan",
    "PagedRequest",
    "Resource",
    "call_options",
    "file_result",
    "plan_page",
    "plan_paged",
    "raw_copy",
]

PathParams = Mapping[str, Union[str, int]]

T = TypeVar("T")


def call_options(
    options: RequestOptions,
    body: Any = None,
    path_params: Optional[PathParams] = None,
    query: Optional[Query] = None,
) -> CallOptions:
    """What the engine runs one call with: the request itself plus the caller's overrides."""
    if not isinstance(options, RequestOptions):
        raise TypeError(f"options must be RequestOptions, not {type(options).__name__}")
    return CallOptions(
        body=body,
        query=query,
        path_params=path_params,
        idempotency_key=options.idempotency_key,
        timeout=options.timeout,
        max_retries=options.max_retries,
        extra_headers=options.extra_headers,
        request_id=options.request_id,
    )


@dataclass(frozen=True)
class FileResult:
    """A binary response (PDF/CSV documents)."""

    content: bytes
    content_type: str
    filename: Optional[str] = None

    def write_to(self, path: str) -> None:
        """Save the document next to your code (or anywhere else)."""
        with open(path, "wb") as handle:
            handle.write(self.content)


def file_result(raw: RawResponse) -> FileResult:
    """The bytes of a ``bare`` route's answer, with their type and file name."""
    return FileResult(
        content=raw.body,
        content_type=raw.content_type or "application/octet-stream",
        filename=filename_from(raw.header("content-disposition")),
    )


class Resource:
    """Base of every namespace on :class:`~oblodai.Oblodai`.

    Every method accepts the fields of :class:`~oblodai.RequestOptions` as trailing keyword
    arguments: ``idempotency_key``, ``timeout`` (seconds, per attempt), ``max_retries``,
    ``extra_headers`` and ``request_id`` (sent as ``X-Request-ID``). Anything else is a TypeError.
    """

    #: Set on the copy :attr:`with_raw_response` hands out, never on the namespace itself.
    _raw_response = False
    #: Routes by ``operationId`` for follow-up calls (polling a long-running operation);
    #: ``None`` means the generated route table.
    _operations: Optional[Mapping[str, RouteSpec]] = None
    #: Parsers of poll answers by model name; ``None`` means the generated models.
    _models: Optional[Parsers] = None

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @property
    def with_raw_response(self) -> Any:
        """The same methods, returning :class:`~oblodai.RawAPIResponse` (status, headers,
        ``request_id``, ``parse()``) instead of the parsed result."""
        return raw_copy(self)

    # -- internals ---------------------------------------------------------------------------

    def _request(
        self,
        route: RouteSpec,
        body: Any,
        options: RequestOptions,
        *,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        parse: Optional[Callable[[Any], T]] = None,
    ) -> Any:
        """Call a route the way its kind asks; the one entry point of generated methods.

        An envelope route returns its ``result``, or ``parse(result)`` when given; a long-running
        operation (:mod:`oblodai.lro`) returns a :class:`~oblodai.core.poller.Job` around that
        value. A paged list (``list_kind="paged"``) returns a lazy :class:`Page` whose items go
        through ``parse``; ``limit``/``offset`` in the body (query for GET) pick the first page.
        A ``bare`` route returns a :class:`FileResult`. Through :attr:`with_raw_response` each
        returns a :class:`RawAPIResponse` whose ``parse()`` gives the same value (for a list, a
        :class:`Page` that starts from the raw response's page).
        """
        if route.bare:
            opts = call_options(options, body, path_params, query)
            if self._raw_response:
                return RawAPIResponse(
                    route, self._transport.call_raw(route, opts), decode=file_result
                )
            return file_result(self._transport.call_raw(route, opts))
        if route.list_kind == "paged":
            return self._paged(plan_paged(route, body, query, options, path_params, parse))
        opts = call_options(options, body, path_params, query)
        parser: Optional[Callable[[Any], Any]] = parse
        plan = plan_job(route, self._operations, self._models)
        if plan is not None:
            parser = self._job_parser(plan, options, parse)
        if self._raw_response:
            return RawAPIResponse(route, self._transport.call_raw(route, opts), parser)
        result = self._transport.call(route, opts)
        return parser(result) if parser is not None else result

    def _paged(self, plan: PagedRequest) -> Any:
        transport = self._transport

        def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            return plan.page(transport.call(plan.route, plan.call_options(page_limit, page_offset)))

        if not self._raw_response:
            return Page(fetch, plan.limit, plan.offset)
        raw = transport.call_raw(plan.route, plan.first_call_options())

        def decode(response: RawResponse) -> Page[Any]:
            page = plan.page(unwrap_result(plan.route, response))
            return Page(fetch, plan.limit, plan.offset, first=page)

        return RawAPIResponse(plan.route, raw, decode=decode)

    def _job_parser(
        self, plan: JobPlan, options: RequestOptions, parse: Optional[Callable[[Any], Any]]
    ) -> Callable[[Any], Job[Any]]:
        transport = self._transport
        follow = poll_options(options)

        def build(result: Any) -> Job[Any]:
            id = job_id(plan, result)

            def poll() -> Any:
                body = {plan.id_field: id}
                answer = transport.call(plan.poll_route, call_options(follow, body))
                return plan.parse(answer) if plan.parse is not None else answer

            def download(route: RouteSpec) -> Callable[[], FileResult]:
                query = {plan.id_field: id}
                return lambda: file_result(
                    transport.call_raw(route, call_options(follow, query=query))
                )

            return Job(
                id,
                parse(result) if parse is not None else result,
                poll,
                download(plan.download_route) if plan.download_route is not None else None,
            )

        return build

    @staticmethod
    def _options(
        body: Any,
        path_params: Optional[PathParams],
        query: Optional[Query],
        options: Mapping[str, Any],
    ) -> CallOptions:
        """The hand-written resources' ``**options`` adapter (until generated resources)."""
        return call_options(options_from_kwargs(options), body, path_params, query)

    def _call(
        self,
        key: str,
        body: Any = None,
        *,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        **options: Any,
    ) -> Any:
        """Call an envelope route and return its ``result``."""
        return self._transport.call(ROUTES[key], self._options(body, path_params, query, options))

    def _plain_list(self, key: str, body: Any = None, **options: Any) -> List[Any]:
        """Call a plain list route (``{items}`` without ``paginate``)."""
        result = self._transport.call(ROUTES[key], self._options(body, None, None, options))
        return as_plain_list(result)

    def _page(
        self,
        key: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        path_params: Optional[PathParams] = None,
        via_query: bool = False,
        **options: Any,
    ) -> Page[Any]:
        """Call a paged list route (``{items, paginate}``); returns a lazy :class:`Page`."""
        plan = plan_page(key, params, via_query, options)

        def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            call_options = plan.call_options(page_limit, page_offset, path_params)
            return _to_page(self._transport.call(plan.route, call_options))

        return Page(fetch, plan.limit, plan.offset)

    def _file(
        self,
        key: str,
        *,
        body: Any = None,
        path_params: Optional[PathParams] = None,
        query: Optional[Query] = None,
        **options: Any,
    ) -> FileResult:
        """Call a ``bare`` route and return its bytes."""
        raw = self._transport.call_raw(
            ROUTES[key], self._options(body, path_params, query, options)
        )
        return file_result(raw)


R = TypeVar("R")


def raw_copy(resource: R) -> R:
    """A shallow copy of a namespace whose ``_request`` answers with raw responses."""
    clone = copy.copy(resource)
    clone._raw_response = True  # type: ignore[attr-defined]
    return clone


@dataclass(frozen=True)
class PagePlan:
    """Everything a paged call needs, worked out once and shared by both client tiers."""

    route: RouteSpec
    use_query: bool
    rest: Mapping[str, Any]
    limit: Optional[int]
    offset: Optional[int]
    options: Mapping[str, Any]

    def call_options(
        self, page_limit: int, page_offset: int, path_params: Optional[PathParams]
    ) -> CallOptions:
        merged = {**self.rest, "limit": page_limit, "offset": page_offset}
        return Resource._options(
            None if self.use_query else merged,
            path_params,
            merged if self.use_query else None,
            self.options,
        )


def plan_page(
    key: str,
    params: Optional[Mapping[str, Any]],
    via_query: bool,
    options: Dict[str, Any],
) -> PagePlan:
    """Split a list call into its paging arguments, its body/query and its per-call options.

    One place for both tiers, so the sync and async ``_page`` cannot disagree about what a list
    call sends.
    """
    route = ROUTES[key]
    rest: Dict[str, Any] = dict(params or {})
    # `history({"limit": 50})` and `history(limit=50)` are both accepted.
    for shortcut in ("limit", "offset"):
        if shortcut in options:
            rest[shortcut] = options.pop(shortcut)
    limit = rest.pop("limit", None)
    offset = rest.pop("offset", None)
    if options.get("idempotency_key") is not None and not route.idempotent:
        # Silently dropping it would be worse: the caller believes the call is deduplicated, and
        # reusing one key across pages would make the core replay page 1 forever.
        raise ConfigError(
            "sdk.idempotency_unsupported",
            f"{route.method} {route.path} does not deduplicate by Idempotency-Key; "
            "remove idempotency_key from this call",
            "idempotency_key",
        )
    page_options = {k: v for k, v in options.items() if k != "idempotency_key"}
    return PagePlan(
        route=route,
        use_query=route.method == "GET" or via_query,
        rest=rest,
        limit=limit,
        offset=offset,
        options=page_options,
    )


@dataclass(frozen=True)
class PagedRequest:
    """A generated paged-list call, worked out once and shared by both client tiers."""

    route: RouteSpec
    #: The request without ``limit``/``offset``; they go into ``query`` for GET, else ``body``.
    body: Dict[str, Any]
    query: Optional[Dict[str, Any]]
    limit: Optional[int]
    offset: Optional[int]
    options: RequestOptions
    path_params: Optional[PathParams]
    parse: Optional[Callable[[Any], Any]]

    @property
    def use_query(self) -> bool:
        return self.route.method == "GET"

    def call_options(self, page_limit: int, page_offset: int) -> CallOptions:
        paging = {"limit": page_limit, "offset": page_offset}
        if self.use_query:
            body = self.body or None
            query: Optional[Dict[str, Any]] = {**(self.query or {}), **paging}
        else:
            body, query = {**self.body, **paging}, self.query
        return call_options(self.options, body, self.path_params, query)

    def first_call_options(self) -> CallOptions:
        """The first page's request, with the same defaults :class:`Page` applies."""
        return self.call_options(
            DEFAULT_PAGE_LIMIT if self.limit is None else self.limit,
            0 if self.offset is None else self.offset,
        )

    def page(self, result: Any) -> PageResult[Any]:
        page = _to_page(result)
        if self.parse is not None:
            page.items = [self.parse(item) for item in page.items]
        return page


def plan_paged(
    route: RouteSpec,
    body: Any,
    query: Optional[Query],
    options: RequestOptions,
    path_params: Optional[PathParams],
    parse: Optional[Callable[[Any], Any]],
) -> PagedRequest:
    """Split a generated list call into its first page and the request every page repeats."""
    if not isinstance(options, RequestOptions):
        raise TypeError(f"options must be RequestOptions, not {type(options).__name__}")
    if body is None:
        rest: Dict[str, Any] = {}
    elif isinstance(body, Mapping):
        rest = dict(body)
    else:
        raise TypeError(f"a list call's body must be a mapping, not {type(body).__name__}")
    rest_query = dict(query) if query is not None else None
    limit = rest.pop("limit", None)
    offset = rest.pop("offset", None)
    if rest_query is not None:
        limit = rest_query.pop("limit", limit)
        offset = rest_query.pop("offset", offset)
    if options.idempotency_key is not None and not route.idempotent:
        # Same rule as plan_page: one key reused across pages would replay page 1 forever.
        raise ConfigError(
            "sdk.idempotency_unsupported",
            f"{route.method} {route.path} does not deduplicate by Idempotency-Key; "
            "remove idempotency_key from this call",
            "idempotency_key",
        )
    return PagedRequest(
        route=route,
        body=rest,
        query=rest_query,
        limit=limit,
        offset=offset,
        options=replace(options, idempotency_key=None),
        path_params=path_params,
        parse=parse,
    )


def _to_page(result: Any) -> PageResult[Any]:
    page = as_page(result)
    paginate: Paginate = page["paginate"]
    return PageResult(list(page["items"]), paginate)


_FILENAME_UTF8 = re.compile(r"filename\*=UTF-8''([^;]+)", re.IGNORECASE)
_FILENAME_PLAIN = re.compile(r'filename="?([^";]+)"?', re.IGNORECASE)


def filename_from(disposition: Optional[str]) -> Optional[str]:
    """Pull the file name out of a ``Content-Disposition`` header."""
    if not disposition:
        return None
    utf8 = _FILENAME_UTF8.search(disposition)
    if utf8:
        return unquote(utf8.group(1))
    plain = _FILENAME_PLAIN.search(disposition)
    return plain.group(1) if plain else None
