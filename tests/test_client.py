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


# ─────────────────────── Идемпотентность v1.1.0 (Idempotency-Key) ───────────────────────


PAYMENT_OK = httpx.Response(200, json={"state": 0, "result": {
    "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
    "payment_status": "check",
}})


def _uuid4_like(value: str) -> bool:
    import uuid as _uuid
    try:
        return str(_uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


@respx.mock
def test_payment_sends_idempotency_key_header_and_no_order_id_injection():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=PAYMENT_OK)
    client = make_sync()
    client.payments.create(amount="10", currency="USD")

    req = route.calls[0].request
    body = json.loads(req.content)
    assert "order_id" not in body, "order_id больше НЕ подставляется автоматически"
    assert _uuid4_like(req.headers["Idempotency-Key"]), "ключ идемпотентности — uuid4 в заголовке"


@respx.mock
def test_payment_idempotency_key_stable_across_retries():
    route = respx.post(f"{BASE}/v1/payment").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"code": "gateway.unavailable", "message": "later"}}),
            PAYMENT_OK,
        ]
    )
    client = make_sync(retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005))
    client.payments.create(amount="10", currency="USD")

    assert route.call_count == 2
    first = route.calls[0].request.headers["Idempotency-Key"]
    second = route.calls[1].request.headers["Idempotency-Key"]
    assert first == second, "Idempotency-Key должен быть одинаков на всех попытках ретрая"
    # а подпись при этом переподписывается на каждой попытке — ключ в неё не входит
    for call in route.calls:
        assert "order_id" not in json.loads(call.request.content)


@respx.mock
def test_payment_caller_idempotency_key_goes_to_header_not_body():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=PAYMENT_OK)
    client = make_sync()
    client.payments.create(amount="10", currency="USD", idempotency_key="my-key-1")

    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "my-key-1"
    assert "idempotency_key" not in json.loads(req.content), \
        "caller-ключ не должен утекать в подписанное тело"


@respx.mock
def test_payment_order_id_passes_through_verbatim():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=PAYMENT_OK)
    client = make_sync()
    client.payments.create(amount="10", currency="USD", order_id="  ord-1  ")

    body = json.loads(route.calls[0].request.content)
    assert body["order_id"] == "  ord-1  ", "order_id уходит как есть, без нормализации"


@respx.mock
def test_transfer_to_personal_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/transfer/to-personal").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"ok": True}})
    )
    client = make_sync()
    client.account.transfer_to_personal(amount="50", currency="USDT")

    req = route.calls[0].request
    assert _uuid4_like(req.headers["Idempotency-Key"])
    assert "order_id" not in json.loads(req.content)


@respx.mock
def test_payout_create_sends_idempotency_key_and_strips_caller_key():
    route = respx.post(f"{BASE}/v1/payout").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "u1", "order_id": "w-1", "amount": "5", "currency": "USDT",
            "address": "T...", "status": "check",
        }})
    )
    client = make_sync()
    client.payouts.create(amount="5", currency="USDT", address="T...", order_id="w-1",
                          idempotency_key="payout-key")

    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "payout-key"
    body = json.loads(req.content)
    assert "idempotency_key" not in body
    assert body["order_id"] == "w-1"


@respx.mock
def test_refund_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/payment/refund").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"uuid": "r1"}})
    )
    client = make_sync()
    client.payments.refund(uuid="p1", amount="10")
    assert _uuid4_like(route.calls[0].request.headers["Idempotency-Key"])


@respx.mock
async def test_async_payment_idempotency_key_header():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=PAYMENT_OK)
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        await client.payments.create(amount="10", currency="USD", idempotency_key="a-key")

    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "a-key"
    body = json.loads(req.content)
    assert "order_id" not in body
    assert "idempotency_key" not in body


@respx.mock
async def test_async_payment_idempotency_key_stable_across_retries():
    route = respx.post(f"{BASE}/v1/payment").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"code": "gateway.unavailable", "message": "later"}}),
            PAYMENT_OK,
        ]
    )
    async with AsyncOblodaiClient(
        public_id="p", secret="s", base_url=BASE,
        retry=RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005),
    ) as client:
        await client.payments.create(amount="10", currency="USD")

    assert route.call_count == 2
    assert (route.calls[0].request.headers["Idempotency-Key"]
            == route.calls[1].request.headers["Idempotency-Key"])


# ─────────────────────── Батчи (v1.1.0) ───────────────────────


@respx.mock
def test_payment_create_batch():
    route = respx.post(f"{BASE}/v1/payment/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b1", "kind": "payments", "count": 2, "status": "pending",
        }})
    )
    client = make_sync()
    sub = client.payments.create_batch(
        [
            {"amount": "10", "currency": "USD", "order_id": "a-1"},
            {"amount": "20", "currency": "EUR", "order_id": "a-2"},
        ],
        on_error="stop",
    )
    assert sub.batch_id == "b1"
    assert sub.status == "pending"

    req = route.calls[0].request
    body = json.loads(req.content)
    assert body["on_error"] == "stop"
    assert [x["order_id"] for x in body["payments"]] == ["a-1", "a-2"]
    assert _uuid4_like(req.headers["Idempotency-Key"]), "submit-батч обёрнут в идемпотентность"


@respx.mock
def test_refunds_create_batch_and_payments_alias():
    route = respx.post(f"{BASE}/v1/refund/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b2", "kind": "refunds", "count": 1, "status": "pending",
        }})
    )
    client = make_sync()
    sub = client.refunds.create_batch([{"uuid": "p1", "reference": "r-1", "amount": "5"}])
    assert sub.kind == "refunds"
    body = json.loads(route.calls[0].request.content)
    assert body["refunds"][0]["reference"] == "r-1"
    assert "on_error" not in body, "on_error не шлётся, если не задан (серверный дефолт continue)"

    # синоним из доки: payments.refund_batch — тот же эндпоинт
    sub2 = client.payments.refund_batch([{"uuid": "p1", "reference": "r-2", "amount": "5"}])
    assert sub2.batch_id == "b2"
    assert route.call_count == 2


@respx.mock
def test_payouts_create_batch_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/payout/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b3", "kind": "payouts", "count": 1, "status": "pending",
        }})
    )
    client = make_sync()
    client.payouts.create_batch([{"amount": "5", "currency": "USDT", "address": "T1", "order_id": "w-1"}],
                                idempotency_key="batch-key")
    assert route.calls[0].request.headers["Idempotency-Key"] == "batch-key"


@respx.mock
def test_batches_info_done_property():
    route = respx.post(f"{BASE}/v1/batch/info").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b1", "kind": "payments", "status": "completed", "on_error": "continue",
            "total": 2, "succeeded": 1, "failed": 1,
            "created_at": "2026-07-15T10:00:00Z", "updated_at": "2026-07-15T10:01:00Z",
            "items": [
                {"idx": 0, "status": "succeeded", "order_id": "a-1",
                 "result": {"uuid": "p1", "order_id": "a-1"}},
                {"idx": 1, "status": "failed", "order_id": "a-2", "error": "payment.unknown_currency"},
            ],
        }})
    )
    client = make_sync()
    info = client.batches.info("b1", limit=100, offset=0)

    assert info.done is True
    assert info.succeeded == 1 and info.failed == 1
    assert info.items[0].result["uuid"] == "p1"
    assert info.items[1].error == "payment.unknown_currency"
    body = json.loads(route.calls[0].request.content)
    assert body == {"batch_id": "b1", "limit": 100, "offset": 0}
    # read-only — без Idempotency-Key
    assert "Idempotency-Key" not in route.calls[0].request.headers


# ─────────────────────── Платёжные ссылки (v1.1.0) ───────────────────────


@respx.mock
def test_payment_links_crud():
    respx.post(f"{BASE}/v1/payment/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "link_id": "l1", "url": "https://pay.example/link/l1",
        }})
    )
    respx.post(f"{BASE}/v1/payment/link/list").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"items": [
            {"link_id": "l1", "title": "Донат", "amount_mode": "open", "currency": "USD",
             "active": True, "url": "https://pay.example/link/l1", "created_at": "2026-07-15T00:00:00Z"},
        ]}})
    )
    respx.post(f"{BASE}/v1/payment/link/info").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "link_id": "l1", "amount_mode": "open", "currency": "USD", "active": True,
            "payments": [{"uuid": "p1", "status": "paid", "amount": "10", "currency": "USD"}],
        }})
    )
    toggle_route = respx.post(f"{BASE}/v1/payment/link/toggle").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"link_id": "l1", "active": False}})
    )
    client = make_sync()

    created = client.payment_links.create(amount_mode="open", currency="USD", title="Донат")
    assert created.link_id == "l1"

    items = client.payment_links.list(limit=10)
    assert items[0].amount_mode == "open"

    info = client.payment_links.info("l1")
    assert info.payments[0].status == "paid"

    toggled = client.payment_links.toggle("l1", active=False)
    assert toggled["active"] is False
    assert json.loads(toggle_route.calls[0].request.content) == {"link_id": "l1", "active": False}

    # синоним из доки
    assert client.links is client.payment_links


@respx.mock
def test_payment_link_public_checkout_unsigned():
    route = respx.post(f"{BASE}/v1/link/l1/checkout").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p9", "order_id": "gen-1", "amount": "10.00", "currency": "USD",
            "payment_status": "check", "url": "https://pay.example/p9",
        }})
    )
    client = make_sync()
    payment = client.payment_links.checkout("l1", amount="10", currency="USD", network="tron")
    assert payment.uuid == "p9"
    req = route.calls[0].request
    assert "X-Signature" not in req.headers, "публичный checkout не подписывается"
    assert json.loads(req.content)["network"] == "tron"


# ─────────────────────── Сплиты (v1.1.0) ───────────────────────


@respx.mock
def test_splits_rules_and_config():
    rule_route = respx.post(f"{BASE}/v1/split/rule").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"rule_id": "sr1", "percent": 10.0}})
    )
    respx.post(f"{BASE}/v1/split/rule/list").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"items": [
            {"rule_id": "sr1", "percent": 10.0, "active": True, "note": "партнёр А",
             "address": "T...", "network": "tron", "reversible": False},
            {"rule_id": "sr2", "percent": 5.0, "active": True,
             "merchant_id": "m2", "reversible": True},
        ]}})
    )
    del_route = respx.post(f"{BASE}/v1/split/rule/delete").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"deleted": True}})
    )
    respx.post(f"{BASE}/v1/split/config/get").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"refund_hold_hours": 24}})
    )
    cfg_route = respx.post(f"{BASE}/v1/split/config/set").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"refund_hold_hours": 48}})
    )
    client = make_sync()

    rule = client.splits.create_rule(address="T...", network="tron", percent=10, note="партнёр А")
    assert rule.rule_id == "sr1"

    # обёртки из доки — тот же эндпоинт
    client.splits.split_to_address(address="T...", network="tron", percent=10)
    client.splits.split_to_merchant(merchant_id="m2", percent=5)
    assert rule_route.call_count == 3
    assert json.loads(rule_route.calls[2].request.content) == {"merchant_id": "m2", "percent": 5}

    rules = client.splits.list_rules()
    assert rules[0].reversible is False and rules[1].reversible is True

    assert client.splits.delete_rule("sr1")["deleted"] is True
    assert json.loads(del_route.calls[0].request.content) == {"rule_id": "sr1"}

    assert client.splits.get_config()["refund_hold_hours"] == 24
    client.splits.set_config(refund_hold_hours=48)
    assert json.loads(cfg_route.calls[0].request.content) == {"refund_hold_hours": 48}


# ─────────────────────── send-email и resolve (v1.1.0) ───────────────────────


@respx.mock
def test_send_email():
    route = respx.post(f"{BASE}/v1/payment/send-email").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "sent": True, "email": "buyer@example.com", "uuid": "p1",
        }})
    )
    client = make_sync()
    res = client.payments.send_email(uuid="p1", email="buyer@example.com")
    assert res["sent"] is True
    body = json.loads(route.calls[0].request.content)
    assert body == {"uuid": "p1", "email": "buyer@example.com"}
    # send-email не обёрнут в идемпотентность на шлюзе — заголовок не шлём
    assert "Idempotency-Key" not in route.calls[0].request.headers


@respx.mock
def test_resolve_accept():
    route = respx.post(f"{BASE}/v1/payment/resolve").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "payment_uuid": "p1", "order_id": "ord-1", "resolution": "accepted",
            "amount_kept": "48.5", "currency": "USDT",
        }})
    )
    client = make_sync()
    res = client.payments.resolve(order_id="ord-1", action="accept")
    assert res.resolution == "accepted"
    assert res.amount_kept == "48.5"
    req = route.calls[0].request
    assert json.loads(req.content) == {"order_id": "ord-1", "action": "accept"}
    assert _uuid4_like(req.headers["Idempotency-Key"]), "resolve обёрнут в идемпотентность"


@respx.mock
def test_resolve_refund():
    route = respx.post(f"{BASE}/v1/payment/resolve").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "payment_uuid": "p1", "order_id": "ord-1", "resolution": "refunded",
            "uuid": "r-payout-1", "amount": "48.5", "currency": "USDT",
            "address": "0xPayer", "status": "check", "is_final": False,
        }})
    )
    client = make_sync()
    res = client.payments.resolve(uuid="p1", action="refund", reference="rf-1",
                                  idempotency_key="res-key")
    assert res.resolution == "refunded"
    assert res.uuid == "r-payout-1"
    assert res.is_final is False
    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "res-key"
    assert json.loads(req.content) == {"uuid": "p1", "action": "refund", "reference": "rf-1"}


# ─────────────────────── Payout-ссылки (v1.1.0) ───────────────────────


PAYOUT_LINK_VIEW = {
    "link_id": "pl1", "status": "funded", "amount": "0.005", "currency": "BTC",
    "network": "bitcoin", "title": "Bonus", "expires_at": "2026-08-14T17:00:00Z",
    "created_at": "2026-07-15T17:00:00Z", "reference": "bonus-42",
}


@respx.mock
def test_payout_link_create_sends_idempotency_header():
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            **PAYOUT_LINK_VIEW,
            "claim_token": "Xk3v" + "a" * 39,
            "claim_url": "https://pay.example/claim/Xk3v",
        }})
    )
    client = make_sync()
    link = client.payout_links.create(
        currency="BTC", network="bitcoin", amount="0.005",
        reference="bonus-42", title="Bonus", expires_in_hours=720,
    )
    assert link.status == "funded"
    assert link.claim_token.startswith("Xk3v")
    assert link.claim_url

    req = route.calls[0].request
    assert _uuid4_like(req.headers["Idempotency-Key"]), \
        "создание ссылки резервирует деньги — ключ идемпотентности обязателен"
    assert "X-Signature" in req.headers, "management-эндпоинт подписывается"
    body = json.loads(req.content)
    assert body["expires_in_hours"] == 720
    assert body["reference"] == "bonus-42"


@respx.mock
def test_payout_link_create_batch_index_aligned():
    respx.post(f"{BASE}/v1/payout/link/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "created": 1, "total": 2,
            "results": [
                {"ok": True, "link": {**PAYOUT_LINK_VIEW, "batch_id": "pb1", "claim_token": "t1"}},
                {"ok": False, "error": "payoutlink.insufficient_funds",
                 "message": "available balance is less than the link amount"},
            ],
        }})
    )
    client = make_sync()
    res = client.payout_links.create_batch([
        {"currency": "BTC", "network": "bitcoin", "amount": "0.005", "expires_in_hours": 24},
        {"currency": "BTC", "network": "bitcoin", "amount": "1000", "expires_in_hours": 24},
    ])
    assert res.created == 1 and res.total == 2
    assert res.results[0].ok is True
    assert res.results[0].link.batch_id == "pb1"
    assert res.results[1].ok is False
    assert res.results[1].error == "payoutlink.insufficient_funds"


# ── Идемпотентность на резервирующих деньги вызовах (v1.2.0) ──
#
# payout/link, payout/link/batch и wallet/blocked-address-refund резервируют баланс.
# Без ключа авто-ретрай по потерянному ответу создавал бы вторую профинансированную ссылку.

PAYOUT_LINK_CREATED = httpx.Response(200, json={"state": 0, "result": {
    **PAYOUT_LINK_VIEW, "claim_token": "tok", "claim_url": "https://pay.example/claim/tok",
}})

PAYOUT_LINK_BATCH_OK = httpx.Response(200, json={"state": 0, "result": {
    "created": 1, "total": 1,
    "results": [{"ok": True, "link": {**PAYOUT_LINK_VIEW, "batch_id": "pb1", "claim_token": "t1"}}],
}})

BLOCKED_REFUND_OK = httpx.Response(200, json={"state": 0, "result": {"uuid": "pay-1"}})

RETRY_FAST = RetryConfig(max_attempts=3, initial_delay=0.001, max_delay=0.005)
UNAVAILABLE = httpx.Response(503, json={"error": {"code": "gateway.unavailable", "message": "later"}})


@respx.mock
def test_payout_link_batch_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/payout/link/batch").mock(return_value=PAYOUT_LINK_BATCH_OK)
    make_sync().payout_links.create_batch([
        {"currency": "BTC", "network": "bitcoin", "amount": "0.005", "expires_in_hours": 24},
    ])
    assert _uuid4_like(route.calls[0].request.headers["Idempotency-Key"])


@respx.mock
def test_blocked_address_refund_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/wallet/blocked-address-refund").mock(return_value=BLOCKED_REFUND_OK)
    make_sync().wallets.blocked_address_refund(uuid="inv-1", address="T1")
    assert _uuid4_like(route.calls[0].request.headers["Idempotency-Key"])


@respx.mock
def test_payout_link_create_key_stable_across_retries():
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        side_effect=[UNAVAILABLE, PAYOUT_LINK_CREATED]
    )
    make_sync(retry=RETRY_FAST).payout_links.create(
        currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24,
    )
    assert route.call_count == 2
    assert (route.calls[0].request.headers["Idempotency-Key"]
            == route.calls[1].request.headers["Idempotency-Key"]), \
        "иначе повтор создал бы вторую профинансированную ссылку"


@respx.mock
def test_payout_link_batch_key_stable_across_retries():
    route = respx.post(f"{BASE}/v1/payout/link/batch").mock(
        side_effect=[UNAVAILABLE, PAYOUT_LINK_BATCH_OK]
    )
    make_sync(retry=RETRY_FAST).payout_links.create_batch([
        {"currency": "BTC", "network": "bitcoin", "amount": "0.005", "expires_in_hours": 24},
    ])
    assert route.call_count == 2
    assert (route.calls[0].request.headers["Idempotency-Key"]
            == route.calls[1].request.headers["Idempotency-Key"])


@respx.mock
def test_blocked_address_refund_key_stable_across_retries():
    route = respx.post(f"{BASE}/v1/wallet/blocked-address-refund").mock(
        side_effect=[UNAVAILABLE, BLOCKED_REFUND_OK]
    )
    make_sync(retry=RETRY_FAST).wallets.blocked_address_refund(uuid="inv-1", address="T1")
    assert route.call_count == 2
    assert (route.calls[0].request.headers["Idempotency-Key"]
            == route.calls[1].request.headers["Idempotency-Key"])


@respx.mock
def test_payout_link_caller_key_goes_to_header_not_body():
    create = respx.post(f"{BASE}/v1/payout/link").mock(return_value=PAYOUT_LINK_CREATED)
    batch = respx.post(f"{BASE}/v1/payout/link/batch").mock(return_value=PAYOUT_LINK_BATCH_OK)
    refund = respx.post(f"{BASE}/v1/wallet/blocked-address-refund").mock(return_value=BLOCKED_REFUND_OK)
    client = make_sync()

    client.payout_links.create(
        currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24,
        idempotency_key="link-key-1",
    )
    client.payout_links.create_batch(
        [{"currency": "BTC", "network": "bitcoin", "amount": "0.005", "expires_in_hours": 24}],
        idempotency_key="batch-key-1",
    )
    client.wallets.blocked_address_refund(uuid="inv-1", address="T1", idempotency_key="refund-key-1")

    req = create.calls[0].request
    assert req.headers["Idempotency-Key"] == "link-key-1"
    assert "idempotency_key" not in json.loads(req.content), \
        "caller-ключ не должен утекать в подписанное тело"
    assert batch.calls[0].request.headers["Idempotency-Key"] == "batch-key-1"
    assert refund.calls[0].request.headers["Idempotency-Key"] == "refund-key-1"


@respx.mock
async def test_async_payout_link_key_stable_across_retries():
    create = respx.post(f"{BASE}/v1/payout/link").mock(
        side_effect=[UNAVAILABLE, PAYOUT_LINK_CREATED]
    )
    batch = respx.post(f"{BASE}/v1/payout/link/batch").mock(return_value=PAYOUT_LINK_BATCH_OK)
    refund = respx.post(f"{BASE}/v1/wallet/blocked-address-refund").mock(return_value=BLOCKED_REFUND_OK)

    async with AsyncOblodaiClient(
        public_id="p", secret="s", base_url=BASE, retry=RETRY_FAST,
    ) as client:
        await client.payout_links.create(
            currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24,
        )
        await client.payout_links.create_batch(
            [{"currency": "BTC", "network": "bitcoin", "amount": "0.005", "expires_in_hours": 24}],
            idempotency_key="async-batch-key",
        )
        await client.wallets.blocked_address_refund(uuid="inv-1", address="T1")

    assert create.call_count == 2
    assert (create.calls[0].request.headers["Idempotency-Key"]
            == create.calls[1].request.headers["Idempotency-Key"])
    assert batch.calls[0].request.headers["Idempotency-Key"] == "async-batch-key"
    assert _uuid4_like(refund.calls[0].request.headers["Idempotency-Key"])


# ── Шлюз УВАЖАЕТ Idempotency-Key на payout-ссылках (коды ответов middleware) ──
#
# /v1/payout/link и /v1/payout/link/batch обёрнуты в idempotency-middleware: повтор с тем же
# ключом реплеит первый ответ и не резервирует баланс второй раз. Отсюда новые коды, которые
# SDK обязан классифицировать правильно: 400/409 — терминальные (ретрай бессмыслен и вреден),
# 503 idempotency.unavailable — временный (стор fail-closed, повтор с ТЕМ ЖЕ ключом безопасен).

IDEM_UNAVAILABLE = httpx.Response(
    503, json={"error": {"code": "idempotency.unavailable",
                         "message": "idempotency store unavailable, retry"}}
)


@respx.mock
def test_payout_link_retry_is_not_disabled_and_replays_same_key_on_idem_unavailable():
    """503 idempotency.unavailable — ретраибелен, и повтор уходит с ТЕМ ЖЕ ключом.

    Отключать авто-ретрай на этих маршрутах — деградация: сервер их дедуплицирует.
    """
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        side_effect=[IDEM_UNAVAILABLE, PAYOUT_LINK_CREATED]
    )
    link = make_sync(retry=RETRY_FAST).payout_links.create(
        currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24,
    )
    assert link.claim_token == "tok"
    assert route.call_count == 2, "503 от стора идемпотентности должен повторяться"
    assert (route.calls[0].request.headers["Idempotency-Key"]
            == route.calls[1].request.headers["Idempotency-Key"]), \
        "ключ обязан пережить внутренний ретрай — иначе сервер не сможет дедуплицировать"


@respx.mock
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "idempotency.key_reused"),
        (400, "idempotency.bad_key"),
        (409, "idempotency.in_progress"),
        (409, "payoutlink.duplicate_reference"),
    ],
)
def test_payout_link_terminal_idempotency_codes_are_not_retried(status, code):
    """400/409 от middleware и дубль reference — терминальны, ретраить их нельзя.

    Дубль reference раньше приходил как 500 `internal`, и SDK крутил его вхолостую;
    теперь это 409 payoutlink.duplicate_reference и цикл ретраев обрывается сразу.
    """
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(status, json={"error": {"code": code, "message": "no"}})
    )
    with pytest.raises(OblodaiAPIError) as ei:
        make_sync(retry=RETRY_FAST).payout_links.create(
            currency="BTC", network="bitcoin", amount="0.005",
            reference="bonus-42", expires_in_hours=24,
        )
    assert ei.value.code == code
    assert ei.value.status == status
    assert ei.value.is_retriable is False
    assert route.call_count == 1, "терминальную ошибку SDK не повторяет"


@respx.mock
def test_payout_link_batch_terminal_duplicate_reference_not_retried():
    route = respx.post(f"{BASE}/v1/payout/link/batch").mock(
        return_value=httpx.Response(409, json={"error": {
            "code": "payoutlink.duplicate_reference", "message": "exists"}})
    )
    with pytest.raises(OblodaiAPIError) as ei:
        make_sync(retry=RETRY_FAST).payout_links.create_batch([
            {"currency": "BTC", "network": "bitcoin", "amount": "0.005",
             "reference": "bonus-42", "expires_in_hours": 24},
        ])
    assert ei.value.code == "payoutlink.duplicate_reference"
    assert route.call_count == 1


@respx.mock
def test_payout_link_replayed_response_is_returned_as_is():
    """Реплей отдаёт ТУ ЖЕ ссылку и тот же claim_token (+ заголовок Idempotent-Replayed)."""
    replayed = httpx.Response(
        200,
        headers={"Idempotent-Replayed": "true"},
        json={"state": 0, "result": {
            **PAYOUT_LINK_VIEW, "claim_token": "tok",
            "claim_url": "https://pay.example/claim/tok",
        }},
    )
    respx.post(f"{BASE}/v1/payout/link").mock(side_effect=[PAYOUT_LINK_CREATED, replayed])
    client = make_sync()
    args = dict(currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24)
    first = client.payout_links.create(**args, idempotency_key="same-key")
    second = client.payout_links.create(**args, idempotency_key="same-key")
    assert first.link_id == second.link_id
    assert first.claim_token == second.claim_token


@respx.mock
def test_payout_link_list_info_cancel():
    respx.post(f"{BASE}/v1/payout/link/list").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"links": [PAYOUT_LINK_VIEW]}})
    )
    respx.post(f"{BASE}/v1/payout/link/info").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            **PAYOUT_LINK_VIEW, "status": "claimed",
            "payout_id": "po1", "claim_address": "bc1q...",
        }})
    )
    cancel_route = respx.post(f"{BASE}/v1/payout/link/cancel").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            **PAYOUT_LINK_VIEW, "status": "cancelled",
        }})
    )
    client = make_sync()

    links = client.payout_links.list(limit=50)
    assert links[0].link_id == "pl1"
    # claim_token в list/info не приходит никогда — модель без него
    assert not hasattr(links[0], "claim_token")

    info = client.payout_links.info("pl1")
    assert info.payout_id == "po1" and info.claim_address == "bc1q..."

    cancelled = client.payout_links.cancel("pl1")
    assert cancelled.status == "cancelled"
    assert json.loads(cancel_route.calls[0].request.content) == {"link_id": "pl1"}


@respx.mock
def test_payout_link_claim_info_public_get_unsigned():
    route = respx.get(f"{BASE}/v1/claim/tok123").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "status": "funded", "amount": "0.005", "currency": "BTC", "network": "bitcoin",
            "title": "Bonus", "expires_at": "2026-08-14T17:00:00Z", "claimable": True,
        }})
    )
    client = make_sync()
    info = client.payout_links.claim_info("tok123")
    assert info.claimable is True
    req = route.calls[0].request
    assert req.method == "GET"
    assert "X-Signature" not in req.headers
    assert "X-Public-Id" not in req.headers


@respx.mock
def test_payout_link_claim_public_post_unsigned():
    route = respx.post(f"{BASE}/v1/claim/tok123").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "status": "claimed", "payout_id": "po1", "amount": "0.005",
            "currency": "BTC", "network": "bitcoin", "address": "bc1q...",
        }})
    )
    client = make_sync()
    res = client.payout_links.claim("tok123", address="bc1q...", memo="m1")
    assert res.status == "claimed"
    assert res.payout_id == "po1"
    req = route.calls[0].request
    assert "X-Signature" not in req.headers, "claim публичный — без подписи"
    assert "Idempotency-Key" not in req.headers
    assert json.loads(req.content) == {"address": "bc1q...", "memo": "m1"}


@respx.mock
async def test_async_payout_link_claim_unsigned():
    route = respx.post(f"{BASE}/v1/claim/tok9").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "status": "claimed", "payout_id": "po2", "amount": "1", "currency": "USDT",
            "network": "tron", "address": "T...",
        }})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        res = await client.payout_links.claim("tok9", address="T...")
    assert res.payout_id == "po2"
    assert "X-Signature" not in route.calls[0].request.headers
    assert json.loads(route.calls[0].request.content) == {"address": "T..."}


# ─────────────────────── Переводы to-user + публичный /v1/pay (v1.2.0) ───────────────────────


TRANSFER_TO_USER_OK = httpx.Response(200, json={"state": 0, "result": {
    "currency": "USDT", "amount": "50", "to_user_id": "5c3f6a1e-0000-0000-0000-000000000001",
    "recipient_balance": "150",
}})

PAY_PUBLIC_SELECT_STATE = {
    "uuid": "p42", "order_id": "o42", "amount": "25.00", "currency": "USD",
    "payment_status": "select", "url": "https://pay.example/p42",
    "accepted": [
        {"currency": "USDT", "network": "tron"},
        {"currency": "BTC", "network": "bitcoin"},
    ],
}

PAY_PUBLIC_FINALIZED = {
    "uuid": "p42", "order_id": "o42", "amount": "25.00", "currency": "USD",
    "payment_status": "check", "address": "TDeposit1", "network": "tron",
    "payer_currency": "USDT", "payer_amount": "25.10",
}


@respx.mock
def test_transfer_to_user_signed_with_idempotency_key():
    route = respx.post(f"{BASE}/v1/transfer/to-user").mock(return_value=TRANSFER_TO_USER_OK)
    client = make_sync()
    res = client.account.transfer_to_user(
        to_user_id="5c3f6a1e-0000-0000-0000-000000000001", amount="50", currency="USDT",
    )
    assert res.to_user_id == "5c3f6a1e-0000-0000-0000-000000000001"
    assert res.recipient_balance == "150"

    req = route.calls[0].request
    assert "X-Signature" in req.headers, "денежный эндпоинт подписывается"
    assert _uuid4_like(req.headers["Idempotency-Key"]), \
        "лестница идемпотентности: SDK шлёт заголовок (авто-uuid4), как payouts.create"
    body = json.loads(req.content)
    assert body == {"to_user_id": "5c3f6a1e-0000-0000-0000-000000000001",
                    "amount": "50", "currency": "USDT"}
    assert "order_id" not in body, "order_id опционален и не подставляется"


@respx.mock
def test_transfer_to_user_caller_key_and_order_id():
    route = respx.post(f"{BASE}/v1/transfer/to-user").mock(return_value=TRANSFER_TO_USER_OK)
    client = make_sync()
    client.account.transfer_to_user(
        to_user_id="5c3f6a1e-0000-0000-0000-000000000001", amount="50", currency="USDT",
        order_id="salary-7", idempotency_key="tr-key-1",
    )
    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "tr-key-1"
    body = json.loads(req.content)
    assert body["order_id"] == "salary-7"
    assert "idempotency_key" not in body, "caller-ключ не утекает в подписанное тело"


@respx.mock
def test_transfer_batch_submits_and_sends_idempotency_key():
    route = respx.post(f"{BASE}/v1/transfer/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "tb1", "kind": "transfers", "count": 2, "status": "pending",
        }})
    )
    client = make_sync()
    sub = client.account.transfer_batch(
        [
            {"to_user_id": "5c3f6a1e-0000-0000-0000-000000000001", "amount": "50", "currency": "USDT"},
            {"to_user_id": "5c3f6a1e-0000-0000-0000-000000000002", "amount": "70", "currency": "USDT"},
        ],
        on_error="continue",
    )
    assert sub.batch_id == "tb1"
    assert sub.kind == "transfers"

    req = route.calls[0].request
    body = json.loads(req.content)
    assert body["on_error"] == "continue"
    assert [x["to_user_id"] for x in body["transfers"]] == [
        "5c3f6a1e-0000-0000-0000-000000000001", "5c3f6a1e-0000-0000-0000-000000000002",
    ]
    assert _uuid4_like(req.headers["Idempotency-Key"]), "submit-батч обёрнут в идемпотентность"


@respx.mock
def test_pay_public_get_unsigned():
    route = respx.get(f"{BASE}/v1/pay/p42").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": PAY_PUBLIC_SELECT_STATE})
    )
    client = make_sync()
    payment = client.payments.public_get("p42")
    assert payment.payment_status == "select"
    assert payment.accepted[0].currency == "USDT"
    assert payment.accepted[0].network == "tron"

    req = route.calls[0].request
    assert req.method == "GET"
    assert "X-Signature" not in req.headers, "публичный /v1/pay/{id} не подписывается"
    assert "X-Public-Id" not in req.headers


@respx.mock
def test_pay_public_select_unsigned():
    route = respx.post(f"{BASE}/v1/pay/p42/select").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": PAY_PUBLIC_FINALIZED})
    )
    client = make_sync()
    payment = client.payments.public_select("p42", currency="USDT", network="tron")
    assert payment.payment_status == "check"
    assert payment.address == "TDeposit1"
    assert payment.payer_currency == "USDT"

    req = route.calls[0].request
    assert req.method == "POST"
    assert "X-Signature" not in req.headers, "публичный select не подписывается"
    assert "Idempotency-Key" not in req.headers
    assert json.loads(req.content) == {"currency": "USDT", "network": "tron"}


@respx.mock
async def test_async_transfer_to_user_signed_with_idempotency_key():
    route = respx.post(f"{BASE}/v1/transfer/to-user").mock(return_value=TRANSFER_TO_USER_OK)
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        res = await client.account.transfer_to_user(
            to_user_id="5c3f6a1e-0000-0000-0000-000000000001", amount="50", currency="USDT",
            idempotency_key="a-tr-key",
        )
    assert res.currency == "USDT"
    req = route.calls[0].request
    assert "X-Signature" in req.headers
    assert req.headers["Idempotency-Key"] == "a-tr-key"
    assert json.loads(req.content) == {"to_user_id": "5c3f6a1e-0000-0000-0000-000000000001",
                                       "amount": "50", "currency": "USDT"}


@respx.mock
async def test_async_transfer_batch():
    route = respx.post(f"{BASE}/v1/transfer/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "tb2", "kind": "transfers", "count": 1, "status": "pending",
        }})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        sub = await client.account.transfer_batch(
            [{"to_user_id": "5c3f6a1e-0000-0000-0000-000000000001", "amount": "5", "currency": "USDT"}]
        )
    assert sub.batch_id == "tb2"
    req = route.calls[0].request
    body = json.loads(req.content)
    assert "on_error" not in body, "on_error не шлётся, если не задан (серверный дефолт continue)"
    assert _uuid4_like(req.headers["Idempotency-Key"])


@respx.mock
async def test_async_pay_public_get_and_select_unsigned():
    get_route = respx.get(f"{BASE}/v1/pay/p42").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": PAY_PUBLIC_SELECT_STATE})
    )
    select_route = respx.post(f"{BASE}/v1/pay/p42/select").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": PAY_PUBLIC_FINALIZED})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        state = await client.payments.public_get("p42")
        assert state.payment_status == "select"
        assert state.accepted[1].network == "bitcoin"

        payment = await client.payments.public_select("p42", currency="USDT", network="tron")
    assert payment.address == "TDeposit1"
    assert get_route.calls[0].request.method == "GET"
    assert "X-Signature" not in get_route.calls[0].request.headers
    req = select_route.calls[0].request
    assert "X-Signature" not in req.headers, "публичные /v1/pay/* не подписываются"
    assert json.loads(req.content) == {"currency": "USDT", "network": "tron"}


@respx.mock
async def test_async_batches_and_payout_links():
    respx.post(f"{BASE}/v1/payout/batch").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b9", "kind": "payouts", "count": 1, "status": "pending",
        }})
    )
    respx.post(f"{BASE}/v1/batch/info").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "batch_id": "b9", "kind": "payouts", "status": "processing",
            "total": 1, "succeeded": 0, "failed": 0, "items": [],
        }})
    )
    link_route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            **PAYOUT_LINK_VIEW, "claim_token": "t", "claim_url": "u",
        }})
    )
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        sub = await client.payouts.create_batch(
            [{"amount": "5", "currency": "USDT", "address": "T1", "order_id": "w-1"}]
        )
        info = await client.batches.info(sub.batch_id)
        assert info.done is False

        link = await client.payout_links.create(
            currency="BTC", network="bitcoin", amount="0.005", expires_in_hours=24,
        )
        assert link.claim_token == "t"
    assert _uuid4_like(link_route.calls[0].request.headers["Idempotency-Key"])
