"""Explicit per-call options, timeouts in seconds, and an X-Request-ID on every request.

Per Ruling 4 the calls go through a test-local ``Resource`` subclass whose routes are built here,
not through the public method names (those are replaced by generated ones).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Dict, List, Optional

import httpx
import pytest

from oblodai import RequestOptions, RouteSpec
from oblodai.aio.base import AsyncResource
from oblodai.contract.types import RouteSpec as LegacyRouteSpec
from oblodai.core.errors import ConfigError, OblodaiError
from oblodai.core.retry import RetryOptions
from oblodai.resources.base import Resource
from tests.support.clients import make_async_client, make_client

BALANCE = RouteSpec(
    method="POST",
    path="/v1/balance",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    operation_id="getBalance",
)
CREATE = RouteSpec(
    method="POST",
    path="/v1/payment",
    auth="key",
    idempotent=True,
    safe=False,
    bare=False,
    operation_id="createPayment",
)
ITEM = RouteSpec(
    method="GET",
    path="/v1/things/{id}",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    operation_id="getThing",
)

NO_OPTIONS = RequestOptions()


class Things(Resource):
    def balance(self, *, options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(BALANCE, {}, options)

    def create(self, body: Dict[str, Any], options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(CREATE, body, options, parse=lambda r: ("parsed", r))

    def item(self, thing_id: str, options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(ITEM, None, options, path_params={"id": thing_id}, query={"x": 1})


class AsyncThings(AsyncResource):
    async def balance(self, options: RequestOptions = NO_OPTIONS) -> Any:
        return await self._request(BALANCE, {}, options, parse=lambda r: ("parsed", r))


def ok(result: Any) -> httpx.Response:
    return httpx.Response(200, json={"state": 0, "result": result})


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.requests: List[httpx.Request] = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0] if self._responses else ok({"balance": []})

    def header(self, name: str, index: int = -1) -> Optional[str]:
        value = self.requests[index].headers.get(name)
        return None if value is None else str(value)

    def timeout(self, index: int = -1) -> Dict[str, Any]:
        return dict(self.requests[index].extensions["timeout"])


def test_route_spec_lives_in_core_and_is_re_exported() -> None:
    assert RouteSpec is LegacyRouteSpec
    assert RouteSpec.__module__ == "oblodai.core.route"
    assert BALANCE.operation_id == "getBalance"
    legacy = LegacyRouteSpec("POST", "/v1/x", "key", False, True, False)
    assert legacy.operation_id == ""


def test_request_options_is_a_frozen_dataclass_with_the_five_options() -> None:
    fields = [f.name for f in dataclasses.fields(RequestOptions)]
    assert fields == ["idempotency_key", "timeout", "max_retries", "extra_headers", "request_id"]
    opts = RequestOptions()
    assert all(getattr(opts, name) is None for name in fields)
    with pytest.raises(dataclasses.FrozenInstanceError):
        opts.timeout = 1.0  # type: ignore[misc]


def test_timeout_is_seconds_and_request_id_is_sent() -> None:
    rec = Recorder()
    c = make_client(rec, timeout=5)
    result = Things(c.transport).balance(options=RequestOptions(request_id="rq-1", timeout=2.5))
    assert result == {"balance": []}
    assert rec.header("x-request-id") == "rq-1"
    assert rec.timeout()["read"] == pytest.approx(2.5)


def test_client_timeout_is_seconds_too() -> None:
    rec = Recorder()
    Things(make_client(rec, timeout=5).transport).balance()
    assert rec.timeout()["read"] == pytest.approx(5.0)
    assert rec.timeout()["connect"] == pytest.approx(5.0)


def test_client_deadline_in_seconds_caps_the_attempt() -> None:
    rec = Recorder()
    Things(make_client(rec, timeout=30, deadline=0.5).transport).balance()
    assert 0 < rec.timeout()["read"] <= 0.5


def test_client_accepts_an_httpx_timeout() -> None:
    rec = Recorder()
    c = make_client(rec, timeout=httpx.Timeout(7.0, connect=2.0))
    Things(c.transport).balance()
    assert rec.timeout()["read"] == pytest.approx(7.0)


def test_a_generated_request_id_is_a_uuid4_and_stays_the_same_across_retries() -> None:
    rec = Recorder(
        httpx.Response(
            503, json={"state": 1, "error": {"code": "db.unavailable", "retryable": True}}
        ),
        ok({"balance": []}),
    )
    c = make_client(rec, retry=RetryOptions(base_delay_ms=1, max_delay_ms=1))
    Things(c.transport).balance()
    assert len(rec.requests) == 2
    first, second = rec.header("x-request-id", 0), rec.header("x-request-id", 1)
    assert first == second
    assert first is not None and uuid.UUID(first).version == 4


def test_every_call_gets_its_own_request_id() -> None:
    rec = Recorder()
    things = Things(make_client(rec).transport)
    things.balance()
    things.balance()
    assert rec.header("x-request-id", 0) != rec.header("x-request-id", 1)


def test_a_request_id_with_a_line_break_is_rejected_before_the_network() -> None:
    rec = Recorder()
    with pytest.raises(ConfigError):
        Things(make_client(rec).transport).balance(
            options=RequestOptions(request_id="a\r\nX-Injected: 1")
        )
    assert rec.requests == []


def test_an_x_request_id_in_extra_headers_is_used_when_request_id_is_not_given() -> None:
    rec = Recorder()
    things = Things(make_client(rec).transport)
    things.balance(options=RequestOptions(extra_headers={"X-Request-Id": "from-header"}))
    assert rec.header("x-request-id") == "from-header"
    assert rec.requests[-1].headers.get_list("x-request-id") == ["from-header"]
    things.balance(
        options=RequestOptions(extra_headers={"X-Request-Id": "h"}, request_id="option-wins")
    )
    assert rec.requests[-1].headers.get_list("x-request-id") == ["option-wins"]


def test_extra_headers_are_merged_over_the_clients() -> None:
    rec = Recorder()
    c = make_client(rec, headers={"X-Trace": "client", "X-Keep": "k"})
    Things(c.transport).balance(options=RequestOptions(extra_headers={"X-Trace": "call"}))
    assert rec.header("x-trace") == "call"
    assert rec.header("x-keep") == "k"


def test_max_retries_overrides_the_client_retry_policy_per_call() -> None:
    unavailable = httpx.Response(
        503, json={"state": 1, "error": {"code": "db.unavailable", "retryable": True}}
    )
    rec = Recorder(unavailable)
    c = make_client(rec, retry=RetryOptions(max_retries=5, base_delay_ms=1, max_delay_ms=1))
    with pytest.raises(OblodaiError):
        Things(c.transport).balance(options=RequestOptions(max_retries=0))
    assert len(rec.requests) == 1
    with pytest.raises(OblodaiError):
        Things(c.transport).balance(options=RequestOptions(max_retries=1))
    assert len(rec.requests) == 3


def test_idempotency_key_option_is_sent_and_parse_is_applied() -> None:
    rec = Recorder(ok({"uuid": "u-1"}))
    result = Things(make_client(rec).transport).create(
        {"amount": "1"}, RequestOptions(idempotency_key="key-000000000001")
    )
    assert result == ("parsed", {"uuid": "u-1"})
    assert rec.header("idempotency-key") == "key-000000000001"


def test_path_params_and_query_are_passed_through() -> None:
    rec = Recorder(ok({"id": "t-1"}))
    assert Things(make_client(rec).transport).item("t-1") == {"id": "t-1"}
    assert rec.requests[-1].url.path == "/v1/things/t-1"
    assert rec.requests[-1].url.params.get("x") == "1"


def test_request_rejects_anything_but_request_options() -> None:
    things = Things(make_client(Recorder()).transport)
    with pytest.raises(TypeError):
        things._request(BALANCE, {}, {"timeout": 1})  # type: ignore[arg-type]


# --- the generated methods take the same options as keyword arguments ----------------------


def test_generated_methods_take_the_option_names() -> None:
    rec = Recorder(ok({"balance": {"merchant": []}}))
    c = make_client(rec, timeout=5)
    c.account.get_balance(request_id="rq-legacy", timeout=2.5, extra_headers={"X-Trace": "t"})
    assert rec.header("x-request-id") == "rq-legacy"
    assert rec.header("x-trace") == "t"
    assert rec.timeout()["read"] == pytest.approx(2.5)


@pytest.mark.parametrize("old", ["timeout_ms", "deadline_ms", "headers"])
def test_unknown_option_is_a_type_error_at_call_time(old: str) -> None:
    rec = Recorder()
    c = make_client(rec)
    with pytest.raises(TypeError):
        c.account.get_balance(**{old: 5})  # type: ignore[arg-type]
    assert rec.requests == []


async def test_async_request_mirrors_the_sync_one() -> None:
    rec = Recorder()
    c = make_async_client(rec, timeout=5)
    result = await AsyncThings(c.transport).balance(
        RequestOptions(request_id="rq-async", timeout=1.5)
    )
    assert result == ("parsed", {"balance": []})
    assert rec.header("x-request-id") == "rq-async"
    assert rec.timeout()["read"] == pytest.approx(1.5)
    await c.aclose()


async def test_async_generated_methods_take_the_option_names() -> None:
    rec = Recorder(ok({"balance": {"merchant": []}}))
    c = make_async_client(rec)
    await c.account.get_balance(request_id="rq-a", timeout=3)
    assert rec.header("x-request-id") == "rq-a"
    with pytest.raises(TypeError):
        await c.account.get_balance(timeout_ms=5)  # type: ignore[call-arg]
    await c.aclose()
