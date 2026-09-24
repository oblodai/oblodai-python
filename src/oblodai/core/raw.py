"""The raw side of a successful call: ``resource.with_raw_response.<method>(...)``."""

from __future__ import annotations

from typing import Any, Callable, Generic, Mapping, Optional, TypeVar

from .request import HEADER_REQUEST_ID
from .route import RouteSpec
from .steps import RawResponse

__all__ = ["RawAPIResponse"]

T = TypeVar("T")

_UNPARSED: Any = object()


class RawAPIResponse(Generic[T]):
    """Status, headers and request id of a 2xx answer; :meth:`parse` gives the usual result.

    An error status still raises, exactly as without ``with_raw_response``.
    """

    def __init__(
        self,
        route: RouteSpec,
        raw: RawResponse,
        parse: Optional[Callable[[Any], T]] = None,
        *,
        decode: Optional[Callable[[RawResponse], Any]] = None,
    ) -> None:
        self._route = route
        self._raw = raw
        self._parse = parse
        #: Turns the response into the value ``parse`` gets; the envelope's ``result`` by default
        #: (a ``bare`` route decodes to its file, a paged one to its first page).
        self._decode = decode
        self._parsed: Any = _UNPARSED

    @property
    def status(self) -> int:
        return self._raw.status

    @property
    def headers(self) -> Mapping[str, str]:
        return self._raw.headers

    @property
    def request_id(self) -> str:
        """The response's ``X-Request-ID``, else the one this SDK sent with the call."""
        return self._raw.header(HEADER_REQUEST_ID) or self._raw.request_id

    @property
    def content(self) -> bytes:
        return self._raw.body

    def header(self, name: str) -> Optional[str]:
        """One header, looked up case-insensitively."""
        return self._raw.header(name)

    def parse(self) -> T:
        """The value the method returns without ``with_raw_response`` (computed once)."""
        if self._parsed is _UNPARSED:
            if self._decode is not None:
                result = self._decode(self._raw)
            else:
                from .engine import unwrap_result

                result = unwrap_result(self._route, self._raw)
            self._parsed = self._parse(result) if self._parse is not None else result
        return self._parsed  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        return (
            f"RawAPIResponse(status={self.status}, request_id={self.request_id!r}, "
            f"route={self._route.key!r})"
        )
