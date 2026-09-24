"""``httpx`` transports that misbehave on purpose: slow drips, oversized bodies, redirects.

``httpx.MockTransport`` answers instantly and ignores the timeout, so none of the rules that
matter under a hostile or wedged server can be tested with it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Iterable, Iterator, List, Optional

import httpx

__all__ = [
    "AsyncDripTransport",
    "DripTransport",
    "RecordingTransport",
    "chunks_of",
]


def chunks_of(total_bytes: int, chunk_bytes: int = 1024 * 1024) -> List[bytes]:
    """``total_bytes`` of filler, split into chunks a streaming body can dribble out."""
    whole, rest = divmod(total_bytes, chunk_bytes)
    out = [b"x" * chunk_bytes for _ in range(whole)]
    if rest:
        out.append(b"x" * rest)
    return out


class _DripStream(httpx.SyncByteStream):
    def __init__(self, chunks: Iterable[bytes], delay: float) -> None:
        self._chunks = list(chunks)
        self._delay = delay

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._chunks:
            if self._delay:
                time.sleep(self._delay)
            yield chunk


class _AsyncDripStream(httpx.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes], delay: float) -> None:
        self._chunks = list(chunks)
        self._delay = delay

    async def __aiter__(self) -> Any:
        for chunk in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk


class DripTransport(httpx.BaseTransport):
    """Answers 200 immediately, then dribbles the body out one chunk at a time."""

    def __init__(self, chunks: Iterable[bytes], delay: float = 0.0) -> None:
        self._chunks = list(chunks)
        self._delay = delay
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(
            200,
            stream=_DripStream(self._chunks, self._delay),
            headers={"content-type": "application/json"},
        )


class AsyncDripTransport(httpx.AsyncBaseTransport):
    """The asynchronous twin of :class:`DripTransport`."""

    def __init__(self, chunks: Iterable[bytes], delay: float = 0.0) -> None:
        self._chunks = list(chunks)
        self._delay = delay
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(
            200,
            stream=_AsyncDripStream(self._chunks, self._delay),
            headers={"content-type": "application/json"},
        )


class RecordingTransport(httpx.BaseTransport):
    """Answers a fixed envelope and remembers the per-request timeout ``httpx`` was handed."""

    def __init__(self, body: bytes = b'{"state":0,"result":{"balance":{"merchant":[]}}}') -> None:
        self._body = body
        self.timeouts: List[Optional[Dict[str, Optional[float]]]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.timeouts.append(request.extensions.get("timeout"))
        return httpx.Response(200, content=self._body, headers={"content-type": "application/json"})
