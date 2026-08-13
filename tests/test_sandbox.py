"""Тесты песочницы (v1.2.0): пять test-only эндпоинтов + подписанный GET с пустым телом."""

import json

import httpx
import pytest
import respx

from oblodai import AsyncOblodaiClient, OblodaiAPIError, OblodaiClient, is_test_key, sign_request

BASE = "https://api.test"


def make_sync(retry=None):
    return OblodaiClient(
        public_id="test_pub1", secret="oblodai_test_sec1", base_url=BASE, retry=retry
    )


DEPOSIT_OK = httpx.Response(
    200,
    json={
        "state": 0,
        "result": {
            "invoice_id": "11111111-1111-1111-1111-111111111111",
            "txid": "sandbox-tx-1",
            "amount": "10.00",
            "confirmations": 0,
        },
    },
)

DELIVERY = {
    "id": "d1",
    "event_type": "payment",
    "url": "https://shop.example/cb",
    "status": "delivered",
    "attempts": 1,
    "last_error": None,
    "payload": {"type": "payment", "status": "paid", "order_id": "o1"},
    "created_at": "2026-07-19T10:00:00Z",
    "updated_at": "2026-07-19T10:00:01Z",
}


# ─────────────────────────── Синхронные ───────────────────────────


@respx.mock
def test_simulate_deposit_minimal_body_and_unwrap():
    route = respx.post(f"{BASE}/v1/sandbox/deposit").mock(return_value=DEPOSIT_OK)
    client = make_sync()
    dep = client.sandbox.simulate_deposit(invoice_id="11111111-1111-1111-1111-111111111111")

    assert dep.txid == "sandbox-tx-1"
    assert dep.confirmations == 0
    req = route.calls[0].request
    assert req.method == "POST"
    # необязательные поля не шлём — «оплатить ровно причитающееся, сразу подтверждено»
    assert json.loads(req.content) == {"invoice_id": "11111111-1111-1111-1111-111111111111"}
    assert req.headers["X-Public-Id"] == "test_pub1"
    assert len(req.headers["X-Signature"]) == 64


@respx.mock
def test_simulate_deposit_full_params():
    route = respx.post(f"{BASE}/v1/sandbox/deposit").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "invoice_id": "inv-1",
                    "txid": "tx-repeat",
                    "amount": "5.00",
                    "confirmations": 2,
                },
            },
        )
    )
    client = make_sync()
    dep = client.sandbox.simulate_deposit(
        invoice_id="inv-1",
        amount="5.00",
        confirmations=2,
        txid="tx-repeat",
    )
    assert dep.confirmations == 2
    assert json.loads(route.calls[0].request.content) == {
        "invoice_id": "inv-1",
        "amount": "5.00",
        "confirmations": 2,
        "txid": "tx-repeat",
    }


@respx.mock
def test_faucet_idempotency_key_is_body_field_not_header():
    route = respx.post(f"{BASE}/v1/sandbox/faucet").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "asset": "USDT",
                    "amount": "1000",
                    "journal_id": "j1",
                },
            },
        )
    )
    client = make_sync()
    res = client.sandbox.faucet(asset="USDT", amount="1000", idempotency_key="fc-1")

    assert res.journal_id == "j1"
    req = route.calls[0].request
    # контракт /v1/sandbox/faucet: idempotency_key — поле ТЕЛА, заголовок не шлётся
    assert json.loads(req.content) == {"asset": "USDT", "amount": "1000", "idempotency_key": "fc-1"}
    assert "Idempotency-Key" not in req.headers


@respx.mock
def test_reset_empty_body():
    route = respx.post(f"{BASE}/v1/sandbox/reset").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "invoices_cancelled": 3,
                    "balances_zeroed": 2,
                },
            },
        )
    )
    client = make_sync()
    res = client.sandbox.reset()
    assert res.invoices_cancelled == 3
    assert res.balances_zeroed == 2
    assert json.loads(route.calls[0].request.content) == {}


@respx.mock
def test_list_webhooks_signed_get_empty_body():
    route = respx.get(f"{BASE}/v1/sandbox/webhooks").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"deliveries": [DELIVERY]}})
    )
    client = make_sync()
    deliveries = client.sandbox.list_webhooks()

    assert deliveries[0].id == "d1"
    assert deliveries[0].payload["status"] == "paid"

    req = route.calls[0].request
    assert req.method == "GET"
    assert req.content == b"", "GET уходит без тела"
    # подпись считается по канонической строке ts\nGET\n/v1/sandbox/webhooks\n<пусто>
    assert req.headers["X-Public-Id"] == "test_pub1"
    ts = req.headers["X-Timestamp"]
    expected = sign_request("oblodai_test_sec1", "GET", "/v1/sandbox/webhooks", "", timestamp=ts)
    assert req.headers["X-Signature"] == expected.signature


@respx.mock
def test_replay_webhook():
    route = respx.post(f"{BASE}/v1/sandbox/webhooks/replay").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "delivery_id": "d1",
                    "requeued": True,
                },
            },
        )
    )
    client = make_sync()
    res = client.sandbox.replay_webhook("d1")
    assert res.requeued is True
    assert json.loads(route.calls[0].request.content) == {"delivery_id": "d1"}


@respx.mock
def test_live_key_gets_403_sandbox_live_key():
    respx.post(f"{BASE}/v1/sandbox/faucet").mock(
        return_value=httpx.Response(
            403,
            json={
                "error": {
                    "code": "sandbox.live_key",
                    "message": "sandbox endpoints require a test key",
                }
            },
        )
    )
    client = OblodaiClient(
        public_id="live_pub", secret="oblodai_live_sec", base_url=BASE, retry=None
    )
    with pytest.raises(OblodaiAPIError) as ei:
        client.sandbox.faucet(asset="USDT", amount="1")
    assert ei.value.code == "sandbox.live_key"
    assert ei.value.status == 403
    assert ei.value.is_retriable is False


def test_is_test_key():
    assert is_test_key("test_abc123") is True
    assert is_test_key("oblodai_pub_live") is False
    assert is_test_key("") is False


# ─────────────────────────── Асинхронные ───────────────────────────


@respx.mock
async def test_async_simulate_deposit_and_faucet():
    dep_route = respx.post(f"{BASE}/v1/sandbox/deposit").mock(return_value=DEPOSIT_OK)
    respx.post(f"{BASE}/v1/sandbox/faucet").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "asset": "BTC",
                    "amount": "0.5",
                    "journal_id": "j2",
                },
            },
        )
    )
    async with AsyncOblodaiClient(
        public_id="test_pub1", secret="oblodai_test_sec1", base_url=BASE, retry=None
    ) as client:
        dep = await client.sandbox.simulate_deposit(
            invoice_id="11111111-1111-1111-1111-111111111111",
            confirmations=1,
        )
        fc = await client.sandbox.faucet(asset="BTC", amount="0.5")

    assert dep.txid == "sandbox-tx-1"
    assert fc.journal_id == "j2"
    body = json.loads(dep_route.calls[0].request.content)
    assert body == {"invoice_id": "11111111-1111-1111-1111-111111111111", "confirmations": 1}


@respx.mock
async def test_async_list_webhooks_signed_get_and_replay():
    get_route = respx.get(f"{BASE}/v1/sandbox/webhooks").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"deliveries": [DELIVERY]}})
    )
    respx.post(f"{BASE}/v1/sandbox/webhooks/replay").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "delivery_id": "d1",
                    "requeued": True,
                },
            },
        )
    )
    async with AsyncOblodaiClient(
        public_id="test_pub1", secret="oblodai_test_sec1", base_url=BASE, retry=None
    ) as client:
        deliveries = await client.sandbox.list_webhooks()
        res = await client.sandbox.replay_webhook(deliveries[0].id)

    assert res.requeued is True
    req = get_route.calls[0].request
    assert req.method == "GET"
    assert req.content == b""
    ts = req.headers["X-Timestamp"]
    expected = sign_request("oblodai_test_sec1", "GET", "/v1/sandbox/webhooks", "", timestamp=ts)
    assert req.headers["X-Signature"] == expected.signature


@respx.mock
async def test_async_reset():
    respx.post(f"{BASE}/v1/sandbox/reset").mock(
        return_value=httpx.Response(
            200,
            json={
                "state": 0,
                "result": {
                    "invoices_cancelled": 0,
                    "balances_zeroed": 0,
                },
            },
        )
    )
    async with AsyncOblodaiClient(
        public_id="test_pub1", secret="oblodai_test_sec1", base_url=BASE, retry=None
    ) as client:
        res = await client.sandbox.reset()
    assert res.invoices_cancelled == 0
