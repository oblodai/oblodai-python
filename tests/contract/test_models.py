"""Generated models versus the golden bodies the core recorded.

Every recorded 2xx answer goes through the SDK method of its route, end to end: it must parse, and
no model on the way may be left with fields it does not know (``extra``) - a field the core
started sending that the contract does not declare fails here. Webhook samples, statuses and
error envelopes are checked against the generated enums and models the same way.
"""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any, Dict, List, Type, cast

import pytest

from oblodai import (
    ROUTES,
    ErrorCode,
    Oblodai,
    PaymentStatus,
    PaymentWebhook,
    PayoutLinkStatus,
    PayoutStatus,
    PayoutWebhook,
    WalletWebhook,
    WebhookDeliveryStatus,
)
from oblodai.core.model import Model
from oblodai.core.pagination import Page
from oblodai.core.poller import Job
from tests.support.coverage import call
from tests.support.fixtures import (
    load_error_samples,
    load_fixtures,
    load_webhook_samples,
    result_of,
)
from tests.support.mock_http import MockHTTP, Scripted

FIXTURES = load_fixtures()
BY_KEY = {spec.key: op for op, spec in ROUTES.items()}

#: Recorded 2xx JSON answers of routes the contract still has.
RECORDED = sorted(
    route
    for route, recorded in FIXTURES.items()
    if 200 <= recorded["status"] < 300
    and "json" in (recorded.get("headers") or {}).get("Content-Type", "")
    and route in BY_KEY
)


#: Recordings older than a required field the core added since (fixtures: 2026-08-26). The answer
#: must fail on exactly that field; a refreshed recording drops its row here.
ADDED_SINCE_RECORDING: Dict[str, str] = {
    "GET /v1/pay/{id}": "fiat_purchase_available",  # 2026-09-23
    "POST /v1/link/{id}/checkout": "method_adjustment",  # 2026-09-06
    "POST /v1/pay/{id}/select": "method_adjustment",
    "POST /v1/payment": "fee_percent",  # 2026-09-10
    "POST /v1/payment/cancel": "fee_percent",
    "POST /v1/payment/history": "fee_percent",
    "POST /v1/payment/info": "fee_percent",
    "POST /v1/sandbox/reset": "payout_links_cancelled",  # 2026-09-24
    "POST /v1/webhooks/deliveries": "cancel_reason",  # 2026-09-24
}


def unknown_fields(value: Any, where: str = "result") -> List[str]:
    """Every ``extra`` field of every model inside ``value``, with its path."""
    out: List[str] = []
    if isinstance(value, Model):
        out.extend(f"{where}.{name}" for name in value.extra)
        for field in dataclasses.fields(cast(Any, value)):
            if field.name != "extra":
                out.extend(unknown_fields(getattr(value, field.name), f"{where}.{field.name}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            out.extend(unknown_fields(item, f"{where}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            out.extend(unknown_fields(item, f"{where}.{key}"))
    return out


def test_there_are_recorded_bodies_to_check() -> None:
    assert len(RECORDED) > 50


@pytest.mark.parametrize("route", RECORDED)
def test_a_recorded_answer_parses_into_its_model_with_no_unknown_fields(route: str) -> None:
    mock = MockHTTP([Scripted(status=200, body=FIXTURES[route]["response"])])
    client = Oblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )
    added = ADDED_SINCE_RECORDING.get(route)
    if added is not None:
        with pytest.raises(KeyError) as missing:
            result = call(client, BY_KEY[route])
            if isinstance(result, Page):
                result.first()
        assert missing.value.args == (added,)
        return
    result = call(client, BY_KEY[route])
    if isinstance(result, Page):
        result = result.first().items
    if isinstance(result, Job):
        result = result.result
    assert result is not None
    assert unknown_fields(result) == [], f"{route}: the contract does not declare these fields"


def _values(enum: Type[Enum]) -> List[str]:
    return [member.value for member in enum]


def test_statuses_in_fixtures_are_in_the_vocabulary() -> None:
    for payment in result_of("POST /v1/payment/history")["items"]:
        assert payment["status"] in _values(PaymentStatus)
    for payout in result_of("POST /v1/payout/history")["items"]:
        assert payout["status"] in _values(PayoutStatus)
    for link in result_of("POST /v1/payout/link/list")["items"]:
        assert link["status"] in _values(PayoutLinkStatus)
    for delivery in result_of("POST /v1/webhooks/deliveries")["items"]:
        assert delivery["status"] in _values(WebhookDeliveryStatus)


WEBHOOK_MODELS: Dict[str, Any] = {
    "payment": PaymentWebhook,
    "payout": PayoutWebhook,
    "wallet": WalletWebhook,
}


def test_webhook_samples_parse_into_their_models() -> None:
    samples = load_webhook_samples()
    assert samples, "no webhook samples recorded"
    for sample in samples:
        body = json.loads(sample["raw"]) if isinstance(sample.get("raw"), str) else sample["body"]
        event = WEBHOOK_MODELS[body["type"]].from_dict(body)
        assert unknown_fields(event, body["type"]) == []


def test_every_recorded_error_code_has_the_documented_envelope() -> None:
    for code, recorded in load_error_samples().items():
        assert code in _values(ErrorCode)
        error = recorded.get("response", {}).get("error", {})
        assert error["code"] == code
        assert isinstance(error["retryable"], bool)
        assert isinstance(error["request_id"], str)
        if recorded["status"] == 429:
            assert error["retry_after"] > 0
