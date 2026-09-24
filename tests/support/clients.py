"""Clients over ``httpx.MockTransport`` with fixed fake credentials and no environment."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from oblodai import AsyncOblodai, Oblodai

Handler = Callable[[httpx.Request], httpx.Response]
AsyncHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]

PUBLIC_ID = "p"
SECRET = "s" * 32


def make_client(handler: Handler, **kw: Any) -> Oblodai:
    transport = httpx.MockTransport(handler)
    return Oblodai(
        public_id=PUBLIC_ID,
        secret=SECRET,
        http_client=httpx.Client(transport=transport),
        env={},
        **kw,
    )


def make_async_client(handler: Handler, **kw: Any) -> AsyncOblodai:
    transport = httpx.MockTransport(handler)
    return AsyncOblodai(
        public_id=PUBLIC_ID,
        secret=SECRET,
        http_client=httpx.AsyncClient(transport=transport),
        env={},
        **kw,
    )
