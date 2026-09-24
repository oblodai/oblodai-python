"""Money never travels as a float: a float in a body is an error before the network.

Per Ruling 4 the calls go through a test-local ``Resource`` subclass, not the public method names.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict, List

import httpx
import pytest

from oblodai import RequestOptions, RouteSpec
from oblodai.aio.base import AsyncResource
from oblodai.core.errors import AmountError, ConfigError
from oblodai.core.request import NON_MONEY_NUMBERS, serialize_body
from oblodai.helpers.money import (
    add_amounts,
    amount_equals,
    compare_amounts,
    is_zero_amount,
    subtract_amounts,
)
from oblodai.resources.base import Resource
from tests.support.clients import make_async_client, make_client

CREATE = RouteSpec(
    method="POST",
    path="/v1/payment",
    auth="key",
    idempotent=True,
    safe=False,
    bare=False,
    operation_id="createPayment",
)


class Payments(Resource):
    def create(self, **body: Any) -> Any:
        return self._request(CREATE, body, RequestOptions())


class AsyncPayments(AsyncResource):
    async def create(self, **body: Any) -> Any:
        return await self._request(CREATE, body, RequestOptions())


class Counter:
    def __init__(self) -> None:
        self.bodies: List[Dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"state": 0, "result": {"uuid": "u"}})


def test_float_amount_is_an_error_before_the_network() -> None:
    handler = Counter()
    c = make_client(handler)
    with pytest.raises(ConfigError) as excinfo:
        Payments(c.transport).create(amount=25.5, currency="USDT", order_id="o1")
    err = excinfo.value
    assert err.code == "sdk.float_amount"
    assert err.field == "amount"
    assert "25.5" in err.message and "Decimal" in err.message
    assert len(handler.bodies) == 0


async def test_float_amount_is_an_error_before_the_network_async() -> None:
    handler = Counter()
    c = make_async_client(handler)
    with pytest.raises(ConfigError) as excinfo:
        await AsyncPayments(c.transport).create(amount=25.5, currency="USDT")
    assert excinfo.value.code == "sdk.float_amount"
    assert len(handler.bodies) == 0


@pytest.mark.parametrize(
    ("body", "path"),
    [
        ({"payments": [{"amount": "1"}, {"amount": 2.0}]}, "payments[1].amount"),
        ({"meta": {"limits": {"max": 0.1}}}, "meta.limits.max"),
        ([1.5], "[0]"),
        ({"amount": float("nan")}, "amount"),
    ],
)
def test_float_nested_in_dicts_and_lists_is_caught_with_its_path(body: Any, path: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        serialize_body(body, "POST")
    assert excinfo.value.code == "sdk.float_amount"
    assert excinfo.value.field == path


def test_decimal_goes_out_as_its_exact_string() -> None:
    handler = Counter()
    c = make_client(handler)
    Payments(c.transport).create(amount=Decimal("25.50"), currency="USDT", order_id="o1")
    assert handler.bodies[0]["amount"] == "25.50"


def test_ints_and_bools_are_not_floats() -> None:
    assert json.loads(serialize_body({"lifetime": 300, "is_refresh": True}, "POST")) == {
        "lifetime": 300,
        "is_refresh": True,
    }


def test_a_percent_the_contract_types_as_a_number_may_be_a_float() -> None:
    body = {"amount": "10", "accuracy_payment_percent": 1.5}
    assert json.loads(serialize_body(body, "POST"))["accuracy_payment_percent"] == 1.5
    nested = {"payments": [{"amount": "1", "accuracy_payment_percent": 0.5}]}
    assert (
        json.loads(serialize_body(nested, "POST"))["payments"][0]["accuracy_payment_percent"] == 0.5
    )


def test_the_float_allowance_is_the_generated_list_of_the_contracts_number_fields() -> None:
    """One source of truth: the generator's list of ``number`` fields of request schemas."""
    from oblodai.generated import money

    assert NON_MONEY_NUMBERS is money.NON_MONEY_NUMBERS
    assert "accuracy_payment_percent" in NON_MONEY_NUMBERS
    for name in NON_MONEY_NUMBERS:
        assert json.loads(serialize_body({name: 0.5}, "POST")) == {name: 0.5}


def test_money_helpers_take_decimal() -> None:
    assert add_amounts(Decimal("1.10"), "2.20") == "3.30"
    assert subtract_amounts("5", Decimal("0.25")) == "4.75"
    assert compare_amounts(Decimal("1.0"), Decimal("1.00")) == 0
    assert amount_equals(Decimal("25"), "25.000000")
    assert is_zero_amount(Decimal("0.000"))


@pytest.mark.parametrize("bad", [1.1, Decimal("NaN"), Decimal("Infinity")])
def test_money_helpers_refuse_float_and_non_finite_decimal(bad: Any) -> None:
    with pytest.raises(AmountError):
        add_amounts(bad, "1")
