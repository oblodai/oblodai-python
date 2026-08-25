"""Asynchronous HTTP engine: the same :class:`CallEngine` steps, performed with ``httpx.AsyncClient``."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, Optional, Type

import httpx

from ..contract.types import RouteSpec
from .engine import (
    CallEngine,
    CallOptions,
    EngineSettings,
    Fail,
    Finish,
    Pause,
    RawResponse,
    Send,
    unwrap_result,
)
from .errors import TransportError

__all__ = ["AsyncTransport"]


class AsyncTransport:
    """One ``httpx.AsyncClient`` plus the shared call rules."""

    def __init__(
        self, settings: EngineSettings, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(follow_redirects=False)

    # -- public API --------------------------------------------------------------------------

    async def call(self, route: RouteSpec, options: Optional[CallOptions] = None) -> Any:
        """Call an envelope route and return its ``result``."""
        raw = await self.execute(route, options or CallOptions())
        return unwrap_result(route, raw)

    async def call_raw(
        self, route: RouteSpec, options: Optional[CallOptions] = None
    ) -> RawResponse:
        """Call a ``bare`` route and return the response bytes."""
        return await self.execute(route, options or CallOptions())

    async def execute(self, route: RouteSpec, options: CallOptions) -> RawResponse:
        engine = CallEngine(route, options, self.settings)
        step = engine.begin()
        while True:
            if isinstance(step, Send):
                try:
                    raw = await self._send(step)
                except TransportError as err:
                    step = engine.on_transport_error(err)
                else:
                    step = engine.on_response(raw)
            elif isinstance(step, Pause):
                # Cancellation is the caller's decision: CancelledError propagates untouched, so
                # `asyncio.timeout(...)` and `task.cancel()` behave as they do anywhere else.
                await asyncio.sleep(step.delay_ms / 1000.0)
                step = engine.on_pause_done()
            elif isinstance(step, Finish):
                return step.response
            else:
                assert isinstance(step, Fail)
                raise step.error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> AsyncTransport:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()

    # -- internals ---------------------------------------------------------------------------

    async def _send(self, step: Send) -> RawResponse:
        request = step.request
        try:
            response = await self._client.request(
                request.method,
                request.url,
                headers=request.headers,
                content=request.content,
                timeout=step.timeout_ms / 1000.0,
                follow_redirects=False,
            )
        except httpx.TimeoutException as err:
            raise TransportError(
                "transport.timeout", f"request timed out after {step.timeout_ms:.0f} ms", err
            ) from err
        except asyncio.CancelledError:
            raise
        except Exception as err:
            raise TransportError("transport.network", f"network error: {err}", err) from err
        return RawResponse(
            status=response.status_code,
            headers=dict(response.headers),
            body=response.content,
        )
