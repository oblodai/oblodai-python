"""The vocabulary the engine and the transports speak: one step at a time, plus the limits.

:class:`CallEngine` never touches a socket; it hands back a :class:`Send`, a :class:`Pause`, a
:class:`Finish` or a :class:`Fail`, and the transport performs it. Everything a transport needs to
perform one correctly - the attempt's byte cap, the deadline-aware reader, the redirect check -
lives here so the sync and async transports cannot implement it differently.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Mapping, Optional, Union

from .envelope import unexpected_redirect
from .errors import ResponseTooLargeError, TransportError
from .request import BuiltRequest

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_JSON_BYTES",
    "BodyReader",
    "Fail",
    "Finish",
    "Pause",
    "RawResponse",
    "Send",
    "Step",
    "assert_not_redirected",
]


@dataclass(frozen=True)
class RawResponse:
    """What the HTTP layer hands back: status, headers, body bytes."""

    status: int
    headers: Mapping[str, str]
    body: bytes
    #: The ``X-Request-ID`` the SDK sent with the call; set by the engine on success.
    request_id: str = ""

    def header(self, name: str) -> Optional[str]:
        want = name.lower()
        for key, value in self.headers.items():
            if key.lower() == want:
                return value
        return None

    @property
    def content_type(self) -> Optional[str]:
        return self.header("content-type")

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


#: How much of a response body the SDK will hold in memory. An envelope route answers with a
#: JSON object the core builds itself; a bare route streams a generated document. Past these a
#: response is not an answer, it is a memory-exhaustion attempt (or a misrouted base URL).
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Send:
    """Perform this request, then call :meth:`CallEngine.on_response` or ``on_transport_error``.

    ``timeout_ms`` bounds the WHOLE attempt - connect, write, and every byte of the response -
    not just the first byte, and ``max_bytes`` bounds what may be read at all.
    """

    request: BuiltRequest
    timeout_ms: float
    max_bytes: int = MAX_JSON_BYTES


class BodyReader:
    """Reads a response body under the attempt's own deadline and size cap.

    ``httpx``' timeout is per socket operation: a server that dribbles one byte every second
    never trips it, so the whole read is timed here instead. Both transports feed the same
    reader, so sync and async cannot disagree about when a response has taken too long or grown
    too big.
    """

    def __init__(self, step: Send, deadline: float) -> None:
        self._step = step
        self._deadline = deadline
        self._chunks: List[bytes] = []
        self._size = 0

    def feed(self, chunk: bytes, http_status: int) -> None:
        if time.monotonic() > self._deadline:
            raise TransportError(
                "transport.timeout",
                f"reading the response exceeded {self._step.timeout_ms:.0f} ms",
            )
        self._size += len(chunk)
        if self._size > self._step.max_bytes:
            raise ResponseTooLargeError(
                f"response body exceeds the {self._step.max_bytes} byte limit for "
                f"{self._step.request.method} {self._step.request.request_uri}",
                http_status,
            )
        self._chunks.append(chunk)

    def finish(self) -> bytes:
        return b"".join(self._chunks)


def assert_not_redirected(requested_url: str, final_url: str, http_status: int) -> None:
    """An injected HTTP client that follows redirects must not do so behind the SDK's back."""
    if final_url and final_url != requested_url:
        raise unexpected_redirect(http_status, final_url)


@dataclass(frozen=True)
class Pause:
    """Wait this long, then call :meth:`CallEngine.on_pause_done`."""

    delay_ms: float


@dataclass(frozen=True)
class Finish:
    """The call succeeded."""

    response: RawResponse


@dataclass(frozen=True)
class Fail:
    """The call failed for good; raise this."""

    error: BaseException


Step = Union[Send, Pause, Finish, Fail]
