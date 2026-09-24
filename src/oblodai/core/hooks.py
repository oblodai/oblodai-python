"""Request and response hooks: plain callables the client calls once per attempt.

Hooks are for observability - metrics, tracing, structured logs. They run synchronously on the
calling thread (on the event loop for :class:`~oblodai.AsyncOblodai`), so keep them cheap; an
exception raised by a hook propagates out of the call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from .signing import HEADER_ADMIN_TOKEN, HEADER_SIGNATURE

__all__ = ["Hooks", "RequestInfo", "ResponseInfo", "redact_headers"]

_SECRET_HEADERS = frozenset(h.lower() for h in (HEADER_SIGNATURE, HEADER_ADMIN_TOKEN))


def redact_headers(headers: Mapping[str, str]) -> Mapping[str, str]:
    """A copy with the signature and the admin token replaced by ``[redacted]``."""
    return {
        name: "[redacted]" if name.lower() in _SECRET_HEADERS else value
        for name, value in headers.items()
    }


@dataclass(frozen=True)
class RequestInfo:
    """One attempt about to be sent."""

    method: str
    url: str
    #: The headers as sent, with the signature and the admin token redacted.
    headers: Mapping[str, str] = field(repr=False)
    #: 1 for the first attempt, 2 for the first retry, and so on.
    attempt: int
    #: ``X-Request-ID`` of the call; the same on every attempt.
    request_id: str
    #: The route's OpenAPI ``operationId`` (empty for routes of the older contract mirror).
    operation_id: str = ""


@dataclass(frozen=True)
class ResponseInfo:
    """How one attempt ended: an HTTP response, or ``status == 0`` and a transport ``error``."""

    request: RequestInfo
    #: HTTP status, or 0 when the attempt produced no response (timeout, network error).
    status: int
    headers: Mapping[str, str] = field(repr=False)
    #: Seconds from sending the attempt to this point.
    elapsed: float
    #: The error this attempt ended with (an error status or a transport failure), else None.
    error: Optional[BaseException] = None


@dataclass(frozen=True)
class Hooks:
    """``Oblodai(..., hooks=Hooks(on_request=..., on_response=...))``; both are optional."""

    on_request: Optional[Callable[[RequestInfo], None]] = None
    on_response: Optional[Callable[[ResponseInfo], None]] = None
