"""Synchronous HTTP engine: performs the steps :class:`CallEngine` asks for, over ``httpx``."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any, Optional, Type

import httpx

from .engine import (
    BodyReader,
    CallEngine,
    CallOptions,
    EngineSettings,
    Fail,
    Finish,
    Pause,
    RawResponse,
    Send,
    assert_not_redirected,
    unwrap_result,
)
from .errors import OblodaiError, TransportError
from .route import RouteSpec

__all__ = ["Transport"]


class Transport:
    """One HTTP client plus the shared call rules. Safe to share across threads."""

    def __init__(
        self, settings: EngineSettings, http_client: Optional[httpx.Client] = None
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(follow_redirects=False)

    # -- public API --------------------------------------------------------------------------

    def call(self, route: RouteSpec, options: Optional[CallOptions] = None) -> Any:
        """Call an envelope route and return its ``result``."""
        raw = self.execute(route, options or CallOptions())
        return unwrap_result(route, raw)

    def call_raw(self, route: RouteSpec, options: Optional[CallOptions] = None) -> RawResponse:
        """Call a ``bare`` route and return the response bytes (status already checked 2xx)."""
        return self.execute(route, options or CallOptions())

    def execute(self, route: RouteSpec, options: CallOptions) -> RawResponse:
        engine = CallEngine(route, options, self.settings)
        step = engine.begin()
        while True:
            if isinstance(step, Send):
                try:
                    raw = self._send(step)
                except TransportError as err:
                    step = engine.on_transport_error(err)
                else:
                    step = engine.on_response(raw)
            elif isinstance(step, Pause):
                time.sleep(step.delay_ms / 1000.0)
                step = engine.on_pause_done()
            elif isinstance(step, Finish):
                return step.response
            else:
                assert isinstance(step, Fail)
                raise step.error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Transport:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    # -- internals ---------------------------------------------------------------------------

    def _send(self, step: Send) -> RawResponse:
        request = step.request
        seconds = step.timeout_ms / 1000.0
        deadline = time.monotonic() + seconds
        try:
            with self._client.stream(
                request.method,
                request.url,
                headers=request.headers,
                content=request.content,
                timeout=seconds,
                follow_redirects=False,
            ) as response:
                assert_not_redirected(request.url, str(response.url), response.status_code)
                reader = BodyReader(step, deadline)
                for chunk in response.iter_bytes():
                    reader.feed(chunk, response.status_code)
                return RawResponse(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=reader.finish(),
                )
        except httpx.TimeoutException as err:
            raise TransportError(
                "transport.timeout", f"request timed out after {step.timeout_ms:.0f} ms", err
            ) from err
        except OblodaiError:
            # A deadline, a size cap or a followed redirect: already the right error, and never
            # to be re-labelled `transport.network` (which is retryable, and these are not).
            raise
        except (httpx.HTTPError, OSError) as err:
            # Only a real transport failure becomes one. A TypeError from inside this SDK is a
            # bug, and dressing it up as a retryable network error would hide it and re-send the
            # request twice more.
            raise TransportError("transport.network", f"network error: {err}", err) from err
