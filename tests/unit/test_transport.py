"""Signing, idempotency, retry classification and clock skew, over a scripted HTTP layer."""

from __future__ import annotations

import re
from typing import Any, Dict

import httpx
import pytest

from oblodai import Oblodai
from oblodai.core.errors import (
    AuthenticationError,
    IdempotencyConflictError,
    OblodaiError,
    RateLimitError,
    TransportError,
    ValidationError,
)
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


def client(mock: MockHTTP, **overrides: Any) -> Oblodai:
    options: Dict[str, Any] = {**CREDS, **overrides}
    return Oblodai(http_client=mock.client, **options)


def test_signs_path_and_query_on_get_and_sends_no_body() -> None:
    mock = MockHTTP(
        [
            ok(
                {
                    "items": [],
                    "paginate": {"total": 0, "per_page": 10, "offset": 0, "has_pages": False},
                }
            )
        ]
    )
    client(mock).sandbox.webhooks({"limit": 10, "offset": 0}).first()
    call = mock.calls[0]
    assert call.url == "https://api.test/v1/sandbox/webhooks?limit=10&offset=0"
    assert call.body is None
    assert call.headers["x-public-id"] == "pk_test_1"
    assert HEX64.match(call.headers["x-signature"])
    assert "content-type" not in call.headers


def test_generates_one_idempotency_key_per_create_and_reuses_it_across_retries() -> None:
    mock = MockHTTP(
        [
            api_error(503, {"code": "db.unavailable", "message": "down", "retryable": True}),
            ok({"uuid": "u"}),
        ]
    )
    client(mock).payments.create({"amount": "1", "currency": "USDT"})
    assert len(mock.calls) == 2
    key = mock.calls[0].headers["idempotency-key"]
    assert re.match(r"^[0-9a-f-]{36}$", key)
    assert mock.calls[1].headers["idempotency-key"] == key
    # Re-signed per attempt: the same key, a fresh signature.
    assert HEX64.match(mock.calls[1].headers["x-signature"])


def test_honours_a_caller_key_and_adds_none_to_read_routes() -> None:
    mock = MockHTTP([ok({"uuid": "u"}), ok({"uuid": "u"})])
    api = client(mock)
    api.payouts.create(
        {"amount": "1", "currency": "USDT", "address": "T", "order_id": "o"},
        idempotency_key="my-key-1",
    )
    api.payments.info({"uuid": "u"})
    assert mock.calls[0].headers["idempotency-key"] == "my-key-1"
    assert "idempotency-key" not in mock.calls[1].headers


def test_does_not_retry_a_non_retryable_error_even_on_a_5xx() -> None:
    mock = MockHTTP([api_error(500, {"code": "internal", "retryable": False})])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).account.balance()
    error = excinfo.value
    assert error.code == "internal"
    assert error.http_status == 500
    assert error.retryable is False
    assert len(mock.calls) == 1


def test_retries_a_retryable_error_and_surfaces_it_after_the_budget() -> None:
    rate_limited = api_error(
        429, {"code": "request.rate_limited", "retryable": True, "retry_after": 0}
    )
    mock = MockHTTP([rate_limited, rate_limited, rate_limited])
    with pytest.raises(RateLimitError) as excinfo:
        client(mock).account.balance()
    assert excinfo.value.retry_after == 0
    assert len(mock.calls) == 3  # 1 + max_retries(2)


def test_retries_a_transport_failure_only_when_the_request_is_safe_to_repeat() -> None:
    boom = Scripted(raises=httpx.ConnectError("connection refused"))

    read = MockHTTP([boom, ok({"balance": {"merchant": []}})])
    client(read).account.balance()  # read route -> retried
    assert len(read.calls) == 2

    write = MockHTTP([boom, ok({})])
    with pytest.raises(TransportError) as excinfo:
        client(write).settings.set_accuracy({"enabled": True})
    assert excinfo.value.code == "transport.network"  # write without a key -> not retried
    assert len(write.calls) == 1

    keyed = MockHTTP([boom, ok({"uuid": "u"})])
    client(keyed).payments.create({"amount": "1", "currency": "USDT"})  # keyed -> retried
    assert len(keyed.calls) == 2


def test_classifies_the_envelope_and_keeps_request_id_and_field() -> None:
    mock = MockHTTP(
        [
            api_error(
                400,
                {
                    "code": "payment.below_minimum",
                    "message": "too small",
                    "field": "amount",
                    "retryable": False,
                    "request_id": "rq-1",
                },
            ),
            api_error(
                401, {"code": "merchant.bad_signature", "message": "bad", "retryable": False}
            ),
            api_error(
                409, {"code": "idempotency.key_reused", "message": "reused", "retryable": False}
            ),
        ]
    )
    api = client(mock, retry=RetryOptions(max_retries=0))
    with pytest.raises(ValidationError) as validation:
        api.payments.create({"amount": "0", "currency": "USDT"})
    assert validation.value.code == "payment.below_minimum"
    assert validation.value.field == "amount"
    assert validation.value.request_id == "rq-1"
    assert validation.value.family == "payment"

    with pytest.raises(AuthenticationError):
        api.account.balance()
    with pytest.raises(IdempotencyConflictError):
        api.payments.create({"amount": "1", "currency": "USDT"})


def test_re_signs_once_with_the_server_clock_when_a_401_reveals_skew() -> None:
    import time
    from email.utils import formatdate

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
    client(mock, retry=RetryOptions(max_retries=0)).account.balance()
    assert len(mock.calls) == 2
    assert abs(int(mock.calls[1].headers["x-timestamp"]) - server_now) < 5


def test_times_out_and_reports_transport_timeout() -> None:
    mock = MockHTTP([Scripted(raises=httpx.ReadTimeout("too slow"))])
    with pytest.raises(TransportError) as excinfo:
        client(mock, retry=RetryOptions(max_retries=0)).account.balance()
    assert excinfo.value.code == "transport.timeout"


def test_one_api_key_signs_money_in_money_out_and_batch_routes_alike() -> None:
    """The merchant has a single key; nothing in the SDK may reach for a second one."""
    mock = MockHTTP([ok({"uuid": "p"}), ok({"uuid": "i"}), ok({"batch_id": "b1"})])
    api = client(mock)
    api.payouts.create({"amount": "1", "currency": "USDT", "address": "T", "order_id": "o"})
    api.payments.create({"amount": "1", "currency": "USDT"})
    api.batches.info({"batch_id": "b1"})
    assert [call.headers["x-public-id"] for call in mock.calls] == ["pk_test_1"] * 3


def test_batches_info_sends_exactly_one_request() -> None:
    """There is no second key to fall back to, so a refusal is a refusal."""
    mock = MockHTTP([api_error(403, {"code": "merchant.frozen", "retryable": False})])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).batches.info({"batch_id": "b1"})
    assert excinfo.value.code == "merchant.frozen"
    assert len(mock.calls) == 1


def test_a_per_call_option_the_sdk_no_longer_has_is_refused_before_a_request() -> None:
    mock = MockHTTP([])
    with pytest.raises(TypeError, match="prefer_payout_key"):
        client(mock).payouts.create(
            {"amount": "1", "currency": "USDT", "address": "T", "order_id": "o"},
            prefer_payout_key=True,
        )
    assert not mock.calls


def test_refuses_a_signed_call_with_no_credentials_but_allows_public_ones() -> None:
    mock = MockHTTP([ok({"currencies": [], "pricing_currencies": []})])
    api = Oblodai(base_url="https://api.test", http_client=mock.client, env={})
    assert api.catalog.currencies()["currencies"] == []
    with pytest.raises(OblodaiError) as excinfo:
        api.account.balance()
    assert excinfo.value.code == "sdk.missing_credentials"


def test_the_user_agent_names_the_sdk_and_the_contract() -> None:
    mock = MockHTTP([ok({"balance": {"merchant": []}})])
    client(mock).account.balance()
    assert mock.calls[0].headers["user-agent"].startswith("oblodai-python/1.3.0 (contract ")


def test_unknown_per_call_options_are_rejected_before_anything_is_sent() -> None:
    mock = MockHTTP([])
    with pytest.raises(TypeError, match="idempotencyKey"):
        client(mock).payments.create({"amount": "1", "currency": "USDT"}, idempotencyKey="k")
    assert mock.calls == []
