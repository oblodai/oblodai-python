"""A scripted ``httpx`` transport: replays responses in order and records every request."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import httpx


@dataclass
class Recorded:
    """One request the SDK actually sent."""

    url: str
    method: str
    headers: Dict[str, str]
    body: Optional[str]

    @property
    def json(self) -> Any:
        return json.loads(self.body) if self.body else None

    @property
    def path(self) -> str:
        return httpx.URL(self.url).path

    def query(self, name: str) -> Optional[str]:
        value = httpx.URL(self.url).params.get(name)
        return None if value is None else str(value)


@dataclass
class Scripted:
    """One scripted answer (or failure)."""

    status: int = 200
    body: Any = None
    text: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    #: Raise this instead of answering (simulates a network failure or a timeout).
    raises: Optional[Exception] = None


def ok(result: Any) -> Scripted:
    """A ``{state: 0, result}`` success."""
    return Scripted(status=200, body={"state": 0, "result": result})


def page(items: Sequence[Any], offset: int, total: int, per_page: int) -> Scripted:
    """A ``{items, paginate}`` page."""
    return ok(
        {
            "items": list(items),
            "paginate": {
                "total": total,
                "per_page": per_page,
                "offset": offset,
                "has_pages": offset + len(items) < total,
            },
        }
    )


def api_error(
    status: int, error: Dict[str, Any], headers: Optional[Dict[str, str]] = None
) -> Scripted:
    """An Oblodai error envelope."""
    return Scripted(status=status, body={"error": error}, headers=headers or {})


def html(status: int, headers: Optional[Dict[str, str]] = None) -> Scripted:
    """A proxy answer with no envelope at all."""
    merged = {"content-type": "text/html"}
    merged.update(headers or {})
    return Scripted(status=status, text="<html>upstream error</html>", headers=merged)


class MockHTTP:
    """Hands out ``httpx`` clients backed by the script."""

    def __init__(self, script: Sequence[Scripted]) -> None:
        self._queue: List[Scripted] = list(script)
        self.calls: List[Recorded] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            Recorded(
                url=str(request.url),
                method=request.method,
                headers={k.lower(): v for k, v in request.headers.items()},
                body=request.content.decode("utf-8") if request.content else None,
            )
        )
        if not self._queue:
            raise AssertionError(f"no scripted response for {request.method} {request.url}")
        nxt = self._queue.pop(0)
        if nxt.raises is not None:
            raise nxt.raises
        content = (
            nxt.text if nxt.text is not None else json.dumps(nxt.body or {"state": 0, "result": {}})
        )
        headers = {"content-type": "application/json"}
        headers.update(nxt.headers)
        return httpx.Response(nxt.status, content=content, headers=headers)

    @property
    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle), follow_redirects=False)

    @property
    def async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(self._handle), follow_redirects=False
        )

    @property
    def last(self) -> Recorded:
        return self.calls[-1]
