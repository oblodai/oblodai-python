"""Shared plumbing for the synchronous resource namespaces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import unquote

from ..contract.models.common import Paginate
from ..contract.routes import ROUTES
from ..core.engine import CallOptions
from ..core.envelope import as_page, as_plain_list
from ..core.pagination import Page, PageResult
from ..core.request import Query
from ..core.transport import Transport

__all__ = ["FileResult", "Resource"]

#: Per-call options every resource method accepts as trailing keyword arguments.
OPTION_KEYS = frozenset({"idempotency_key", "timeout_ms", "deadline_ms", "prefer_payout_key"})

PathParams = Mapping[str, Union[str, int]]


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


class Resource:
    """Base of every namespace on :class:`~oblodai.Oblodai`.

    Every method accepts the same trailing keyword arguments:

    ``idempotency_key``
        Your own key; generated automatically on create routes when omitted, and rejected on
        routes the core does not deduplicate.
    ``timeout_ms``
        Per-attempt timeout.
    ``deadline_ms``
        Overall budget for the call including retries.
    ``prefer_payout_key``
        Sign with the payout key on a route that accepts either key kind.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    # -- internals ---------------------------------------------------------------------------

    @staticmethod
    def _options(
        body: Any,
        path_params: Optional[PathParams],
        query: Optional[Query],
        options: Mapping[str, Any],
    ) -> CallOptions:
        unknown = sorted(set(options) - OPTION_KEYS)
        if unknown:
            raise TypeError(
                f"unexpected keyword argument(s) {', '.join(unknown)}; "
                f"resource methods accept {', '.join(sorted(OPTION_KEYS))}"
            )
        return CallOptions(
            body=body,
            query=query,
            path_params=path_params,
            idempotency_key=options.get("idempotency_key"),
            prefer_payout_key=bool(options.get("prefer_payout_key", False)),
            timeout_ms=options.get("timeout_ms"),
            deadline_ms=options.get("deadline_ms"),
        )

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

        def fetch(page_limit: int, page_offset: int) -> PageResult[Any]:
            merged = {**rest, "limit": page_limit, "offset": page_offset}
            call_options = self._options(
                None if use_query else merged,
                path_params,
                merged if use_query else None,
                page_options,
            )
            return _to_page(self._transport.call(route, call_options))

        return Page(fetch, limit, offset)

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
        return FileResult(
            content=raw.body,
            content_type=raw.content_type or "application/octet-stream",
            filename=filename_from(raw.header("content-disposition")),
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
