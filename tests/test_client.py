"""Тесты sync и async клиентов через respx (мок httpx)."""

import json

import httpx
import pytest
import respx

from oblodai import (
    AsyncOblodaiClient,
    OblodaiAPIError,
    OblodaiClient,
    RetryConfig,
)

BASE = "https://api.test"


def make_sync(retry=None):
    return OblodaiClient(public_id="pub_1", secret="sec_1", base_url=BASE, retry=retry)


# ─────────────────────────── Синхронные ───────────────────────────


@respx.mock
def test_sync_signs_and_unwraps():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = make_sync()
    payment = client.payments.create(amount="10", currency="USD", order_id="o1")

    assert payment.uuid == "p1"
    assert payment.payment_status == "check"

    req = route.calls[0].request
    assert req.headers["X-Public-Id"] == "pub_1"
    assert req.headers["X-Timestamp"].isdigit()
    assert len(req.headers["X-Signature"]) == 64


@respx.mock
def test_sync_api_error():
    respx.post(f"{BASE}/v1/payout").mock(
        return_value=httpx.Response(409, json={"error": {"code": "payout.insufficient_funds", "message": "no"}})
    )
    client = make_sync()
    with pytest.raises(OblodaiAPIError) as ei:
        client.payouts.create(amount="5", currency="USDT", address="T...", order_id="x")
    assert ei.value.code == "payout.insufficient_funds"
    assert ei.value.status == 409
    assert ei.value.is_retriable is False


@respx.mock
def test_sync_retries_503_then_success():
    route = respx.post(f"{BASE}/v1/balance").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"code": "gateway.unavailable", "message": "later"}}),
            httpx.Response(200, json={"state": 0, "result": {"balance": {"merchant": []}}}),
        ]
    )
    client = make_sync(retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005))
    bal = client.account.balance()
    assert bal.merchant == []
    assert route.call_count == 2


@respx.mock
def test_sync_does_not_retry_400():
    route = respx.post(f"{BASE}/v1/balance").mock(
        return_value=httpx.Response(400, json={"error": {"code": "request.bad_json", "message": "bad"}})
    )
    client = make_sync(retry=RetryConfig(max_attempts=3, initial_delay=0.001))
    with pytest.raises(OblodaiAPIError) as ei:
        client.account.balance()
    assert ei.value.code == "request.bad_json"
    assert route.call_count == 1


@respx.mock
def test_sync_public_rate_no_signature():
    route = respx.post(f"{BASE}/v1/exchange-rate/list").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": [{"from": "ETH", "to": "USDT", "course": "3450"}]})
    )
    client = make_sync()
    rates = client.rates.list("ETH")
    assert rates[0].course == "3450"
    assert rates[0].from_ == "ETH"
    assert "X-Signature" not in route.calls[0].request.headers


@respx.mock
def test_sync_webhook_register_no_envelope():
    respx.post(f"{BASE}/v1/webhooks").mock(
        return_value=httpx.Response(201, json={"endpoint_id": "e1", "url": "https://x", "secret": "s1"})
    )
    client = make_sync()
    reg = client.webhooks.register("https://x")
    assert reg.secret == "s1"
    assert reg.endpoint_id == "e1"


def test_from_env(monkeypatch):
    monkeypatch.setenv("OBLODAI_PUBLIC_ID", "pub_env")
    monkeypatch.setenv("OBLODAI_SECRET", "sec_env")
    monkeypatch.setenv("OBLODAI_BASE_URL", "https://env.example")

    client = OblodaiClient.from_env()
    assert client._http._base_url == "https://env.example"
    client.close()

    monkeypatch.delenv("OBLODAI_PUBLIC_ID")
    with pytest.raises(ValueError):
        OblodaiClient.from_env()


@respx.mock
def test_sync_currencies_public_get():
    route = respx.get(f"{BASE}/v1/currencies").mock(
        return_value=httpx.Response(200, json={"currencies": [
            {"symbol": "USDT", "decimals": 6, "networks": [
                {"network": "tron", "kind": "token", "contract": "T...", "min_confirmations": 20,
                 "available": True, "deposit_available": True, "payout_available": True},
            ]},
        ]})
    )
    client = make_sync()
    cur = client.rates.currencies()
    assert cur[0].symbol == "USDT"
    assert cur[0].networks[0].network == "tron"
    assert route.calls[0].request.method == "GET"
    assert "X-Signature" not in route.calls[0].request.headers


@respx.mock
def test_sync_429_surfaces_body_message():
    respx.post(f"{BASE}/v1/balance").mock(
        return_value=httpx.Response(429, json={"state": 1, "message": "rate limit exceeded"},
                                    headers={"Retry-After": "60"})
    )
    client = make_sync(retry=None)
    with pytest.raises(OblodaiAPIError) as ei:
        client.account.balance()
    assert ei.value.code == "http.429"
    assert ei.value.message == "rate limit exceeded"
    assert ei.value.retry_after == 60.0


@respx.mock
def test_sync_429_honors_retry_after_and_retries():
    route = respx.post(f"{BASE}/v1/balance").mock(
        side_effect=[
            httpx.Response(429, json={"state": 1, "message": "rate limit exceeded"},
                          headers={"Retry-After": "0"}),
            httpx.Response(200, json={"state": 0, "result": {"balance": {"merchant": []}}}),
        ]
    )
    client = make_sync(retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005))
    bal = client.account.balance()
    assert bal.merchant == []
    assert route.call_count == 2


@respx.mock
def test_sync_mass_payout_partial():
    respx.post(f"{BASE}/v1/payout/mass").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"items": [
            {"uuid": "u1", "order_id": "p-1", "status": "process", "is_final": False, "success": True},
            {"order_id": "p-2", "success": False, "message": "insufficient"},
        ]}})
    )
    client = make_sync()
    res = client.payouts.create_mass([
        {"amount": "25", "currency": "USDT", "network": "tron", "address": "T1", "order_id": "p-1"},
        {"amount": "10", "currency": "USDT", "network": "tron", "address": "T2", "order_id": "p-2"},
    ])
    assert res.items[0].success is True
    assert res.items[1].success is False
    assert res.items[1].message == "insufficient"


# ─────────────────────────── Асинхронные ───────────────────────────


@respx.mock
async def test_async_signs_and_unwraps():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "pa", "order_id": "oa", "amount": "10.00", "currency": "USD", "payment_status": "check",
        }})
    )
    async with AsyncOblodaiClient(public_id="pub_1", secret="sec_1", base_url=BASE, retry=None) as client:
        payment = await client.payments.create(amount="10", currency="USD", order_id="oa")
    assert payment.uuid == "pa"
    assert route.calls[0].request.headers["X-Public-Id"] == "pub_1"


@respx.mock
async def test_async_retries_503():
    route = respx.post(f"{BASE}/v1/balance").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"code": "x.unavailable", "message": "later"}}),
            httpx.Response(200, json={"state": 0, "result": {"balance": {"merchant": []}}}),
        ]
    )
    async with AsyncOblodaiClient(
        public_id="p", secret="s", base_url=BASE,
        retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005),
    ) as client:
        bal = await client.account.balance()
    assert bal.merchant == []
    assert route.call_count == 2


@respx.mock
async def test_async_api_error():
    respx.post(f"{BASE}/v1/payout").mock(
        return_value=httpx.Response(409, json={"error": {"code": "payout.funds_maturing", "message": "wait"}})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(OblodaiAPIError) as ei:
            await client.payouts.create(amount="5", currency="USDT", address="T", order_id="x")
    assert ei.value.code == "payout.funds_maturing"
    assert ei.value.is_retriable is False


# ─────────────────────── Авто-идемпотентность (order_id) ───────────────────────


@respx.mock
def test_payment_injects_order_id_when_omitted():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = make_sync()
    client.payments.create(amount="10", currency="USD")

    body = json.loads(route.calls[0].request.content)
    assert body.get("order_id"), "order_id должен быть подставлен, когда не задан"
    assert body["order_id"].startswith("idem-")


@respx.mock
def test_payment_same_order_id_across_503_retry():
    route = respx.post(f"{BASE}/v1/payment").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"code": "gateway.unavailable", "message": "later"}}),
            httpx.Response(200, json={"state": 0, "result": {
                "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
                "payment_status": "check",
            }}),
        ]
    )
    client = make_sync(retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005))
    client.payments.create(amount="10", currency="USD")

    assert route.call_count == 2
    first = json.loads(route.calls[0].request.content)["order_id"]
    second = json.loads(route.calls[1].request.content)["order_id"]
    assert first.startswith("idem-")
    assert first == second, "order_id должен быть одинаковым на обеих попытках ретрая"


@respx.mock
def test_payment_keeps_explicit_order_id():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "mine", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = make_sync()
    client.payments.create(amount="10", currency="USD", order_id="mine")

    body = json.loads(route.calls[0].request.content)
    assert body["order_id"] == "mine"


@respx.mock
def test_transfer_to_personal_injects_order_id():
    route = respx.post(f"{BASE}/v1/transfer/to-personal").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"ok": True}})
    )
    client = make_sync()
    client.account.transfer_to_personal(amount="50", currency="USDT")

    body = json.loads(route.calls[0].request.content)
    assert body.get("order_id", "").startswith("idem-")


@respx.mock
def test_payment_injects_order_id_when_whitespace():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = make_sync()
    client.payments.create(amount="10", currency="USD", order_id="   ")

    body = json.loads(route.calls[0].request.content)
    assert body.get("order_id", "").startswith("idem-"), \
        "order_id из одних пробелов должен считаться отсутствующим и нормализоваться"


@respx.mock
def test_payment_keeps_real_order_id_alongside_whitespace_fix():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "ord-1", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = make_sync()
    client.payments.create(amount="10", currency="USD", order_id="ord-1")

    body = json.loads(route.calls[0].request.content)
    assert body["order_id"] == "ord-1", "реальный order_id должен сохраняться без изменений"


@respx.mock
async def test_async_payment_injects_order_id_when_whitespace():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "pa", "order_id": "oa", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        await client.payments.create(amount="10", currency="USD", order_id="   ")

    body = json.loads(route.calls[0].request.content)
    assert body.get("order_id", "").startswith("idem-")


@respx.mock
async def test_async_payment_injects_order_id():
    route = respx.post(f"{BASE}/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "pa", "order_id": "oa", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        await client.payments.create(amount="10", currency="USD")

    body = json.loads(route.calls[0].request.content)
    assert body.get("order_id", "").startswith("idem-")
