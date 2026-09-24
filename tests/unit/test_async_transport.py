"""The asynchronous tier on its own terms.

``tests/contract`` proves the async namespaces call the same routes; these prove the async
transport applies the same RULES - retries, one key per logical call, skew correction, deadlines -
rather than inheriting them by assumption. The engine is shared, but the transport is not.
"""

from __future__ import annotations

import asyncio
import re
import time
from email.utils import formatdate
from typing import Any, Dict

import httpx
import pytest

from oblodai.aio import AsyncOblodai
from oblodai.core.errors import ConfigError, RateLimitError, TransportError
from oblodai.core.retry import RetryOptions
from tests.support.mock_http import MockHTTP, Scripted, api_error, ok

CREDS: Dict[str, Any] = {
    "public_id": "pk_test_1",
    "secret": "secret-1",
    "base_url": "https://api.test",
    "retry": RetryOptions(base_delay_ms=1, max_delay_ms=2),
    "env": {},
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def client(mock: MockHTTP, **overrides: Any) -> AsyncOblodai:
    return AsyncOblodai(http_client=mock.async_client, **{**CREDS, **overrides})


async def test_signs_every_attempt_and_reuses_one_idempotency_key_across_retries() -> None:
    mock = MockHTTP(
        [
            api_error(503, {"code": "db.unavailable", "message": "down", "retryable": True}),
            ok({"uuid": "u"}),
        ]
    )
    await client(mock).payments.create({"amount": "1", "currency": "USDT"})
    assert len(mock.calls) == 2
    key = mock.calls[0].headers["idempotency-key"]
    assert mock.calls[1].headers["idempotency-key"] == key
    # Re-signed per attempt (a fresh timestamp), never re-sent verbatim.
    assert HEX64.match(mock.calls[1].headers["x-signature"])
    assert "x-timestamp" in mock.calls[1].headers


async def test_does_not_repeat_an_unkeyed_write_after_a_transport_failure() -> None:
    """The one rule that separates a lost response from a double spend."""
    mock = MockHTTP([Scripted(raises=httpx.ConnectError("refused")), ok({})])
    with pytest.raises(TransportError):
        await client(mock).settings.set_accuracy({"enabled": True})
    assert len(mock.calls) == 1


async def test_surfaces_the_core_error_after_the_retry_budget() -> None:
    limited = api_error(429, {"code": "request.rate_limited", "retryable": True, "retry_after": 0})
    mock = MockHTTP([limited, limited, limited])
    with pytest.raises(RateLimitError):
        await client(mock).account.balance()
    assert len(mock.calls) == 3


async def test_re_signs_once_with_the_server_clock_when_a_401_reveals_skew() -> None:
    server_now = int(time.time()) + 3600
    mock = MockHTTP(
        [
            api_error(
                401,
                {"code": "merchant.bad_signature", "retryable": False},
                {"date": formatdate(server_now, usegmt=True)},
            ),
            ok({"balance": {"merchant": []}}),
        ]
    )
    await client(mock, retry=RetryOptions(max_retries=0)).account.balance()
    assert len(mock.calls) == 2
    assert abs(int(mock.calls[1].headers["x-timestamp"]) - server_now) < 5


async def test_walks_every_page_with_async_for_and_sends_no_key() -> None:
    def page(offset: int, has_pages: bool) -> Scripted:
        return ok(
            {
                "items": [{"uuid": f"u{offset}"}],
                "paginate": {
                    "total": 2,
                    "per_page": 1,
                    "offset": offset,
                    "has_pages": has_pages,
                },
            }
        )

    mock = MockHTTP([page(0, True), page(1, False)])
    seen = [item["uuid"] async for item in client(mock).payments.history({"limit": 1})]
    assert seen == ["u0", "u1"]
    assert all("idempotency-key" not in call.headers for call in mock.calls)


async def test_a_list_method_refuses_a_caller_idempotency_key_here_too() -> None:
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).payments.history({}, idempotency_key="k")
    assert excinfo.value.code == "sdk.idempotency_unsupported"
    assert mock.calls == []


async def test_awaiting_a_page_object_fetches_only_the_first_page() -> None:
    mock = MockHTTP(
        [
            ok(
                {
                    "items": [{"uuid": "u0"}],
                    "paginate": {"total": 9, "per_page": 1, "offset": 0, "has_pages": True},
                }
            )
        ]
    )
    page = await client(mock).payments.history({"limit": 1})
    assert page.total == 9
    assert len(mock.calls) == 1


async def test_a_bare_route_comes_back_as_bytes_with_its_filename() -> None:
    mock = MockHTTP(
        [
            Scripted(
                status=200,
                text="%PDF-1.4",
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="statement.pdf"',
                },
            )
        ]
    )
    document = await client(mock).documents.statement({"from": "2026-01-01"})
    assert document.content.startswith(b"%PDF")
    assert document.filename == "statement.pdf"
    assert document.content_type == "application/pdf"


async def test_cancellation_is_the_callers_decision_and_is_not_swallowed() -> None:
    """A cancelled task must raise CancelledError, not a TransportError that looks retryable."""

    async def handle(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json={"state": 0, "result": {}})

    injected = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    api = AsyncOblodai(http_client=injected, **CREDS)
    task = asyncio.ensure_future(api.account.balance(timeout=5))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await api.aclose()


async def test_the_async_client_closes_only_the_pool_it_owns() -> None:
    mock = MockHTTP([ok({"balance": {"merchant": []}})])
    injected = mock.async_client
    async with AsyncOblodai(http_client=injected, **CREDS) as api:
        await api.account.balance()
    assert injected.is_closed is False
    await injected.aclose()


async def test_a_programming_error_is_not_dressed_up_as_a_network_failure_here_either() -> None:
    mock = MockHTTP([Scripted(raises=TypeError("a bug, not a socket")), ok({})])
    with pytest.raises(TypeError):
        await client(mock).account.balance()
    assert len(mock.calls) == 1
