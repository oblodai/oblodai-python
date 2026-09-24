"""Raw responses, ``with_options`` and request/response hooks.

Per Ruling 4 the calls go through a test-local ``Resource`` subclass whose routes are built here,
not through the public method names (those are replaced by generated ones).
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest

from oblodai import (
    AsyncOblodai,
    Hooks,
    Oblodai,
    RawAPIResponse,
    RequestInfo,
    RequestOptions,
    ResponseInfo,
    RetryOptions,
    RouteSpec,
)
from oblodai.aio.base import AsyncResource
from oblodai.core.errors import TransportError, UnavailableError
from oblodai.resources.base import Resource
from tests.support.clients import PUBLIC_ID, SECRET, make_async_client, make_client

BALANCE = RouteSpec(
    method="POST",
    path="/v1/balance",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    operation_id="getBalance",
)

NO_OPTIONS = RequestOptions()


class Balance:
    def __init__(self, result: Dict[str, Any]) -> None:
        self.items = result["balance"]

    @classmethod
    def from_dict(cls, result: Dict[str, Any]) -> Balance:
        return cls(result)


class Account(Resource):
    def get_balance(self, options: RequestOptions = NO_OPTIONS) -> Balance:
        return self._request(BALANCE, {}, options, parse=Balance.from_dict)  # type: ignore[no-any-return]

    def raw_result(self, options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(BALANCE, {}, options)


class AsyncAccount(AsyncResource):
    async def get_balance(self, options: RequestOptions = NO_OPTIONS) -> Balance:
        return await self._request(BALANCE, {}, options, parse=Balance.from_dict)  # type: ignore[no-any-return]


def ok(result: Any, **headers: str) -> httpx.Response:
    return httpx.Response(200, json={"state": 0, "result": result}, headers=headers)


def unavailable() -> httpx.Response:
    return httpx.Response(
        503,
        json={"error": {"code": "upstream.unavailable", "message": "down", "retryable": True}},
    )


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.requests: List[httpx.Request] = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0] if self._responses else ok({"balance": [1]})


# --- with_raw_response --------------------------------------------------------------------------


def test_with_raw_response_exposes_status_headers_request_id_and_parse() -> None:
    rec = Recorder(ok({"balance": [7]}, **{"x-request-id": "srv-1", "x-extra": "e"}))
    c = make_client(rec)
    raw = Account(c.transport).with_raw_response.get_balance()
    assert isinstance(raw, RawAPIResponse)
    assert raw.status == 200
    assert raw.headers["x-extra"] == "e"
    assert raw.request_id == "srv-1"
    parsed = raw.parse()
    assert isinstance(parsed, Balance)
    assert parsed.items == [7]


def test_raw_request_id_falls_back_to_the_id_the_sdk_sent() -> None:
    rec = Recorder(ok({"balance": []}))
    c = make_client(rec)
    raw = Account(c.transport).with_raw_response.get_balance(RequestOptions(request_id="mine"))
    assert raw.request_id == "mine"
    assert rec.requests[0].headers["x-request-id"] == "mine"


def test_raw_without_parse_returns_the_unwrapped_result() -> None:
    c = make_client(Recorder(ok({"balance": [1]})))
    assert Account(c.transport).with_raw_response.raw_result().parse() == {"balance": [1]}


def test_with_raw_response_does_not_switch_the_resource_itself() -> None:
    c = make_client(Recorder())
    account = Account(c.transport)
    assert isinstance(account.with_raw_response.get_balance(), RawAPIResponse)
    assert isinstance(account.get_balance(), Balance)


def test_raw_mode_still_raises_on_an_error_status() -> None:
    c = make_client(Recorder(unavailable()), retry=RetryOptions(max_retries=0))
    with pytest.raises(UnavailableError):
        Account(c.transport).with_raw_response.get_balance()


async def test_async_with_raw_response() -> None:
    rec = Recorder(ok({"balance": [3]}, **{"x-request-id": "srv-2"}))
    c = make_async_client(rec)
    raw = await AsyncAccount(c.transport).with_raw_response.get_balance()
    assert raw.status == 200
    assert raw.request_id == "srv-2"
    assert raw.parse().items == [3]


# --- with_options -------------------------------------------------------------------------------


def _read_timeout(request: httpx.Request) -> float:
    return float(request.extensions["timeout"]["read"])


def test_with_options_changes_only_the_copy() -> None:
    rec = Recorder()
    c = make_client(rec, timeout=5)
    fast = c.with_options(timeout=1)
    assert isinstance(fast, Oblodai)
    assert fast is not c
    Account(fast.transport).get_balance()
    Account(c.transport).get_balance()
    assert _read_timeout(rec.requests[0]) == pytest.approx(1)
    assert _read_timeout(rec.requests[1]) == pytest.approx(5)
    assert c.transport.settings.timeout == 5


def test_with_options_shares_the_http_pool_and_closing_the_copy_keeps_it_open() -> None:
    rec = Recorder()
    http = httpx.Client(transport=httpx.MockTransport(rec))
    c = Oblodai(public_id=PUBLIC_ID, secret=SECRET, http_client=http, env={})
    copy = c.with_options(max_retries=0)
    assert copy.transport._client is c.transport._client
    copy.close()
    Account(c.transport).get_balance()
    assert not http.is_closed


def test_with_options_max_retries_and_extra_headers() -> None:
    rec = Recorder(unavailable(), unavailable(), ok({"balance": []}))
    c = make_client(rec, headers={"X-Base": "b"})
    strict = c.with_options(max_retries=0, extra_headers={"X-Tenant": "t1"})
    with pytest.raises(UnavailableError):
        Account(strict.transport).get_balance()
    assert len(rec.requests) == 1
    assert rec.requests[0].headers["x-tenant"] == "t1"
    assert rec.requests[0].headers["x-base"] == "b"
    Account(c.transport).get_balance()
    assert "x-tenant" not in rec.requests[-1].headers


def test_with_options_keeps_the_namespaces() -> None:
    c = make_client(Recorder())
    copy = c.with_options(timeout=2)
    assert copy.payments._transport is copy.transport
    assert copy.base_url == c.base_url


async def test_async_with_options() -> None:
    rec = Recorder()
    c = make_async_client(rec, timeout=5)
    fast = c.with_options(timeout=1)
    assert isinstance(fast, AsyncOblodai)
    await AsyncAccount(fast.transport).get_balance()
    await AsyncAccount(c.transport).get_balance()
    assert _read_timeout(rec.requests[0]) == pytest.approx(1)
    assert _read_timeout(rec.requests[1]) == pytest.approx(5)


# --- hooks --------------------------------------------------------------------------------------


class Seen:
    def __init__(self) -> None:
        self.requests: List[RequestInfo] = []
        self.responses: List[ResponseInfo] = []

    def hooks(self) -> Hooks:
        return Hooks(on_request=self.requests.append, on_response=self.responses.append)


def test_hooks_fire_once_per_attempt() -> None:
    seen = Seen()
    rec = Recorder(unavailable(), ok({"balance": []}))
    c = make_client(rec, hooks=seen.hooks(), retry=RetryOptions(base_delay_ms=0))
    Account(c.transport).get_balance()
    assert len(rec.requests) == 2
    assert [r.attempt for r in seen.requests] == [1, 2]
    assert [r.status for r in seen.responses] == [503, 200]
    first = seen.requests[0]
    assert first.method == "POST"
    assert first.url.endswith("/v1/balance")
    assert first.operation_id == "getBalance"
    assert first.request_id == seen.requests[1].request_id
    assert first.request_id == rec.requests[0].headers["x-request-id"]
    assert seen.responses[1].request is seen.requests[1]
    assert seen.responses[1].elapsed >= 0


def test_hook_request_headers_hide_the_signature() -> None:
    seen = Seen()
    c = make_client(Recorder(), hooks=seen.hooks())
    Account(c.transport).get_balance()
    headers = {k.lower(): v for k, v in seen.requests[0].headers.items()}
    assert headers["x-signature"] == "[redacted]"
    assert headers["x-public-id"] == PUBLIC_ID


def test_on_response_sees_a_transport_error_attempt() -> None:
    seen = Seen()
    calls: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("boom", request=request)
        return ok({"balance": []})

    c = make_client(handler, hooks=seen.hooks(), retry=RetryOptions(base_delay_ms=0))
    Account(c.transport).get_balance()
    assert [r.status for r in seen.responses] == [0, 200]
    assert isinstance(seen.responses[0].error, TransportError)
    assert seen.responses[1].error is None


def test_with_options_keeps_the_hooks() -> None:
    seen = Seen()
    c = make_client(Recorder(), hooks=seen.hooks())
    Account(c.with_options(timeout=3).transport).get_balance()
    assert len(seen.requests) == 1


async def test_async_hooks_fire_once_per_attempt() -> None:
    seen = Seen()
    rec = Recorder(unavailable(), ok({"balance": []}))
    c = make_async_client(rec, hooks=seen.hooks(), retry=RetryOptions(base_delay_ms=0))
    await AsyncAccount(c.transport).get_balance()
    assert [r.status for r in seen.responses] == [503, 200]
    assert len(seen.requests) == 2
