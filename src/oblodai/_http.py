"""Синхронный и асинхронный HTTP-клиенты на httpx.

Оба используют общее ядро из ``_transport`` (подпись, разбор, backoff) и отличаются лишь тем, как
делают HTTP-вызов и паузу между ретраями.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from ._transport import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    RetryConfig,
    backoff_delay,
    logger,
    parse_response,
    prepare_request,
    should_retry,
)
from .errors import OblodaiAPIError, OblodaiConnectionError, OblodaiTimeoutError


def _retry_reason(status: int) -> str:
    """Человекочитаемая причина ретрая по статусу (без секретов/тел)."""
    if status == 429:
        return "429 rate limit"
    if status >= 500:
        return "5xx"
    return f"http {status}"


class SyncHTTPClient:
    def __init__(
        self,
        public_id: str,
        secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retry: Optional[RetryConfig] = RetryConfig(),
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        if not public_id:
            raise ValueError("public_id обязателен")
        if not secret:
            raise ValueError("secret обязателен")
        self._public_id = public_id
        self._secret = secret
        self._base_url = base_url
        self._retry = retry
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None

    def request(self, path: str, payload: Any = None) -> Any:
        return self._execute(path, payload, signed=True)

    def request_public(self, path: str, payload: Any = None, method: str = "POST") -> Any:
        return self._execute(path, payload, signed=False, method=method)

    def _execute(self, path: str, payload: Any, signed: bool, method: str = "POST") -> Any:
        attempts = self._retry.max_attempts if self._retry else 1
        attempt = 0
        while True:
            attempt += 1
            prep = prepare_request(
                base_url=self._base_url,
                public_id=self._public_id,
                secret=self._secret,
                path=path,
                payload=payload,
                signed=signed,
                method=method,
            )
            logger.debug("oblodai: -> %s %s (attempt %d/%d)", method, path, attempt, attempts)
            started = time.monotonic()
            try:
                resp = self._client.request(
                    prep.method, prep.url, headers=prep.headers, content=prep.body
                )
            except httpx.TimeoutException as e:
                err: OblodaiConnectionError = OblodaiTimeoutError(
                    f"Таймаут запроса {path}", e
                )
                if self._retry and attempt < attempts:
                    delay = backoff_delay(attempt, self._retry)
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000), "network timeout", attempt + 1, attempts,
                    )
                    time.sleep(delay)
                    continue
                logger.warning("oblodai: %s %s failed: network timeout", method, path)
                raise err
            except httpx.HTTPError as e:
                if self._retry and attempt < attempts:
                    delay = backoff_delay(attempt, self._retry)
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000), "network", attempt + 1, attempts,
                    )
                    time.sleep(delay)
                    continue
                logger.warning("oblodai: %s %s failed: network error", method, path)
                raise OblodaiConnectionError(f"Сетевая ошибка при запросе {path}", e)

            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.debug(
                "oblodai: <- %d %s %s %dms", resp.status_code, method, path, elapsed_ms
            )
            try:
                return parse_response(
                    resp.status_code, resp.text, resp.headers.get("Retry-After")
                )
            except OblodaiAPIError as api_err:
                if self._retry and should_retry(api_err, attempt, attempts):
                    # Уважаем Retry-After от сервера (напр. 429), иначе — собственный backoff.
                    # Retry-After — прямое указание сервера, поэтому НЕ зажимаем его до max_delay
                    # (иначе `Retry-After: 60` превратился бы в 30с и мы били бы раньше срока).
                    # Ставим лишь абсолютный потолок в 300с как защиту от абсурдных значений.
                    delay = (
                        min(api_err.retry_after, 300.0)
                        if api_err.retry_after is not None
                        else backoff_delay(attempt, self._retry)
                    )
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000),
                        _retry_reason(api_err.status), attempt + 1, attempts,
                    )
                    time.sleep(delay)
                    continue
                logger.warning(
                    "oblodai: %s %s failed: %d %s", method, path, api_err.status, api_err.code
                )
                raise

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SyncHTTPClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncHTTPClient:
    def __init__(
        self,
        public_id: str,
        secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retry: Optional[RetryConfig] = RetryConfig(),
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not public_id:
            raise ValueError("public_id обязателен")
        if not secret:
            raise ValueError("secret обязателен")
        self._public_id = public_id
        self._secret = secret
        self._base_url = base_url
        self._retry = retry
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = http_client is None

    async def request(self, path: str, payload: Any = None) -> Any:
        return await self._execute(path, payload, signed=True)

    async def request_public(self, path: str, payload: Any = None, method: str = "POST") -> Any:
        return await self._execute(path, payload, signed=False, method=method)

    async def _execute(self, path: str, payload: Any, signed: bool, method: str = "POST") -> Any:
        attempts = self._retry.max_attempts if self._retry else 1
        attempt = 0
        while True:
            attempt += 1
            prep = prepare_request(
                base_url=self._base_url,
                public_id=self._public_id,
                secret=self._secret,
                path=path,
                payload=payload,
                signed=signed,
                method=method,
            )
            logger.debug("oblodai: -> %s %s (attempt %d/%d)", method, path, attempt, attempts)
            started = time.monotonic()
            try:
                resp = await self._client.request(
                    prep.method, prep.url, headers=prep.headers, content=prep.body
                )
            except httpx.TimeoutException as e:
                if self._retry and attempt < attempts:
                    delay = backoff_delay(attempt, self._retry)
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000), "network timeout", attempt + 1, attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("oblodai: %s %s failed: network timeout", method, path)
                raise OblodaiTimeoutError(f"Таймаут запроса {path}", e)
            except httpx.HTTPError as e:
                if self._retry and attempt < attempts:
                    delay = backoff_delay(attempt, self._retry)
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000), "network", attempt + 1, attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning("oblodai: %s %s failed: network error", method, path)
                raise OblodaiConnectionError(f"Сетевая ошибка при запросе {path}", e)

            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.debug(
                "oblodai: <- %d %s %s %dms", resp.status_code, method, path, elapsed_ms
            )
            try:
                return parse_response(
                    resp.status_code, resp.text, resp.headers.get("Retry-After")
                )
            except OblodaiAPIError as api_err:
                if self._retry and should_retry(api_err, attempt, attempts):
                    # Уважаем Retry-After от сервера (напр. 429), иначе — собственный backoff.
                    # Retry-After — прямое указание сервера, поэтому НЕ зажимаем его до max_delay
                    # (иначе `Retry-After: 60` превратился бы в 30с и мы били бы раньше срока).
                    # Ставим лишь абсолютный потолок в 300с как защиту от абсурдных значений.
                    delay = (
                        min(api_err.retry_after, 300.0)
                        if api_err.retry_after is not None
                        else backoff_delay(attempt, self._retry)
                    )
                    logger.warning(
                        "oblodai: retrying %s %s in %dms (%s; attempt %d/%d)",
                        method, path, int(delay * 1000),
                        _retry_reason(api_err.status), attempt + 1, attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.warning(
                    "oblodai: %s %s failed: %d %s", method, path, api_err.status, api_err.code
                )
                raise

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncHTTPClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
