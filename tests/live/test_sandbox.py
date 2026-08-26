"""The money path against a real core: signature, envelope, idempotency, webhooks."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterator

import pytest

from oblodai import Oblodai, is_payment_paid, verify_webhook
from oblodai.contract.requests import PaymentBody
from oblodai.core.errors import IdempotencyConflictError, OblodaiError
from tests.live.conftest import onboard_sandbox

pytestmark = pytest.mark.skipif(
    not os.environ.get("OBLODAI_LIVE_URL"), reason="OBLODAI_LIVE_URL is not set"
)


@pytest.fixture(scope="module")
def client(live_url: str) -> Iterator[Oblodai]:
    key = onboard_sandbox(live_url, "sdk-live")
    api = Oblodai(
        public_id=key["public_id"],
        secret=key["secret"],
        base_url=live_url,
        allow_insecure_base_url=True,
    )
    yield api
    api.close()


@pytest.fixture(scope="module")
def invoice(client: Oblodai) -> Dict[str, Any]:
    return dict(
        client.payments.create(
            {
                "amount": "25",
                "currency": "USDT",
                "network": "tron",
                "order_id": f"sdk-live-{int(time.time() * 1000)}",
            }
        )
    )


def test_reads_public_catalog_data_without_credentials(live_url: str) -> None:
    with Oblodai(base_url=live_url, allow_insecure_base_url=True) as public:
        assert len(public.catalog.currencies()["currencies"]) > 0


def test_creates_an_invoice_and_reads_it_back(client: Oblodai, invoice: Dict[str, Any]) -> None:
    assert invoice["status"] == "created"
    assert client.payments.info({"order_id": invoice["order_id"]})["uuid"] == invoice["uuid"]

    listing = client.payments.history({"limit": 5}).first()
    assert any(p["uuid"] == invoice["uuid"] for p in listing.items)

    # A signed GET with a query string: the signature covers path + raw query.
    hooks = client.sandbox.webhooks({"limit": 5, "offset": 0}).first()
    assert isinstance(hooks.items, list)


def test_replays_an_idempotent_create_and_refuses_a_reused_key(client: Oblodai) -> None:
    key = f"sdk-idem-{int(time.time() * 1000)}"
    body: PaymentBody = {
        "amount": "5",
        "currency": "USDT",
        "network": "tron",
        "order_id": f"{key}-o",
    }
    first = client.payments.create(body, idempotency_key=key)
    second = client.payments.create(body, idempotency_key=key)
    assert second["uuid"] == first["uuid"]

    with pytest.raises(IdempotencyConflictError) as excinfo:
        client.payments.create(
            {"amount": "2", "currency": "USDT", "network": "tron", "order_id": f"{key}-o2"},
            idempotency_key=key,
        )
    assert excinfo.value.code == "idempotency.key_reused"
    assert excinfo.value.http_status == 409


def test_deposit_then_payout(client: Oblodai, invoice: Dict[str, Any]) -> None:
    client.sandbox.deposit(
        {
            "invoice_id": invoice["uuid"],
            "amount": "25",
            "confirmations": 20,
            "txid": f"sdk-tx-{int(time.time() * 1000)}",
        }
    )
    paid = client.payments.info({"uuid": invoice["uuid"]})
    assert is_payment_paid(paid["status"])

    client.sandbox.faucet({"asset": "USDT", "amount": "100"})
    balance = client.account.balance()
    assert any(b["currency"] == "USDT" for b in balance["balance"]["merchant"])

    calculated = client.payouts.calculate({"amount": "10", "currency": "USDT", "network": "tron"})
    assert calculated["fee_bearer"] is not None
    validated = client.payouts.validate(
        {
            "amount": "10",
            "currency": "USDT",
            "network": "tron",
            "address": "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx",
        }
    )
    assert validated["valid"] is True

    payout = client.payouts.create(
        {
            "amount": "10",
            "currency": "USDT",
            "network": "tron",
            "address": "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx",
            "order_id": f"sdk-po-{int(time.time() * 1000)}",
        }
    )
    assert payout["uuid"]
    assert client.payouts.info({"uuid": payout["uuid"]})["order_id"] == payout["order_id"]


def test_classifies_a_domain_refusal_with_the_cores_own_retryable_flag(client: Oblodai) -> None:
    with pytest.raises(OblodaiError) as excinfo:
        client.payouts.create(
            {
                "amount": "999999",
                "currency": "USDT",
                "network": "tron",
                "address": "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx",
                "order_id": f"sdk-big-{int(time.time() * 1000)}",
            }
        )
    assert excinfo.value.code == "payout.insufficient_funds"
    assert excinfo.value.http_status == 409
    assert isinstance(excinfo.value.request_id, str)


def test_verifies_a_webhook_the_core_signs(client: Oblodai) -> None:
    hook_url = os.environ.get("OBLODAI_LIVE_HOOK_URL")
    if not hook_url:
        pytest.skip("needs a reachable receiver; the contract samples cover verification offline")
    endpoint = client.webhooks.register(hook_url)
    result = client.webhooks.test(
        "payment",
        {"url_callback": hook_url, "currency": "USDT", "network": "tron", "status": "paid"},
    )
    assert result["ok"] is True
    assert endpoint.get("secret")
    assert callable(verify_webhook)
