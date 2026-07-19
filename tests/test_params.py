"""Тесты белых списков полей create-методов (sync и async).

Смысл: опечатка в имени денежного поля должна падать ``TypeError`` ДО подписи и отправки,
а не молча менять смысл операции на стороне шлюза (тот игнорирует неизвестные ключи JSON).
"""

import json

import httpx
import pytest
import respx

from oblodai import AsyncOblodaiClient, OblodaiClient
from oblodai._params import (
    PAYMENT_FIELDS,
    PAYMENT_LINK_FIELDS,
    PAYOUT_FIELDS,
    PAYOUT_LINK_FIELDS,
    SPLIT_RULE_FIELDS,
)

BASE = "https://api.test"


def make_sync():
    return OblodaiClient(public_id="pub_1", secret="sec_1", base_url=BASE, retry=None)


def _payment_ok():
    return httpx.Response(200, json={"state": 0, "result": {
        "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
        "payment_status": "check",
    }})


def _payout_ok():
    return httpx.Response(200, json={"state": 0, "result": {
        "uuid": "w1", "order_id": "o1", "amount": "5", "currency": "USDT",
        "address": "T...", "status": "check",
    }})


# ─────────────────────── Неизвестное поле → TypeError ───────────────────────


@respx.mock
def test_payment_typo_raises_before_request():
    """Опечатка в ``amount`` роняет вызов и НЕ уходит в сеть."""
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=_payment_ok())
    with pytest.raises(TypeError) as ei:
        make_sync().payments.create(amont="10", currency="USD", order_id="o1")
    assert "amont" in str(ei.value)
    assert route.call_count == 0  # до сети дело не дошло


@respx.mock
def test_payment_typo_message_suggests_and_lists():
    with pytest.raises(TypeError) as ei:
        make_sync().payments.create(amount="10", currency="USD", lifetme=600)
    msg = str(ei.value)
    assert "payments.create()" in msg
    assert "'lifetme'" in msg
    assert "'lifetime'" in msg          # подсказка «возможно, имелось в виду»
    assert "Допустимые поля" in msg
    assert "accuracy_payment_percent" in msg


@respx.mock
def test_payment_reports_all_unknown_fields_at_once():
    with pytest.raises(TypeError) as ei:
        make_sync().payments.create(amount="1", currency="USD", lifetme=600, netwrok="tron")
    msg = str(ei.value)
    assert "'lifetme'" in msg and "'netwrok'" in msg
    assert "неизвестные поля" in msg


@respx.mock
def test_payout_typo_raises():
    route = respx.post(f"{BASE}/v1/payout").mock(return_value=_payout_ok())
    with pytest.raises(TypeError) as ei:
        make_sync().payouts.create(
            amount="5", currency="USDT", adress="T...", order_id="w-1", network="tron"
        )
    assert "'adress'" in str(ei.value) and "'address'" in str(ei.value)
    assert route.call_count == 0


@respx.mock
def test_payout_link_typo_raises():
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "link_id": "l1", "status": "funded", "amount": "25",
            "currency": "USDT", "network": "tron",
        }})
    )
    with pytest.raises(TypeError) as ei:
        make_sync().payout_links.create(
            currency="USDT", network="tron", amount="25", expires_in_hour=720
        )
    # именно этот класс опечатки раньше молча давал срок жизни 1 час
    assert "'expires_in_hour'" in str(ei.value) and "'expires_in_hours'" in str(ei.value)
    assert route.call_count == 0


@respx.mock
def test_payment_link_typo_raises():
    route = respx.post(f"{BASE}/v1/payment/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"link_id": "l1", "url": "u"}})
    )
    with pytest.raises(TypeError) as ei:
        make_sync().payment_links.create(amount_mode="fixed", currency="USD", amount_fixt="10")
    assert "'amount_fixt'" in str(ei.value) and "'amount_fixed'" in str(ei.value)
    assert route.call_count == 0


@respx.mock
def test_split_rule_typo_raises():
    route = respx.post(f"{BASE}/v1/split/rule").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"rule_id": "r1", "percent": 10}})
    )
    with pytest.raises(TypeError) as ei:
        make_sync().splits.create_rule(address="T...", network="tron", percnt=10)
    assert "'percnt'" in str(ei.value) and "'percent'" in str(ei.value)
    assert route.call_count == 0


@respx.mock
def test_payment_link_rejects_idempotency_key():
    """Management-эндпоинт денег не двигает — SDK-kwarg тут не принимается."""
    with pytest.raises(TypeError) as ei:
        make_sync().payment_links.create(amount_mode="open", currency="USD", idempotency_key="k")
    assert "'idempotency_key'" in str(ei.value)


# ─────────────────────── Известные поля работают как раньше ───────────────────────


@respx.mock
def test_payment_all_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=_payment_ok())
    body = {f: "x" for f in PAYMENT_FIELDS}
    make_sync().payments.create(**body)
    sent = json.loads(route.calls[0].request.content)
    assert sent == body                      # тело байт-в-байт то же, что передали


@respx.mock
def test_payment_idempotency_key_still_header_only():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=_payment_ok())
    make_sync().payments.create(amount="10", currency="USD", order_id="o1", idempotency_key="my-key")
    req = route.calls[0].request
    assert req.headers["Idempotency-Key"] == "my-key"
    assert "idempotency_key" not in json.loads(req.content)


@respx.mock
def test_payout_all_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payout").mock(return_value=_payout_ok())
    body = {f: "x" for f in PAYOUT_FIELDS}
    make_sync().payouts.create(**body)
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
def test_payout_link_all_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "link_id": "l1", "status": "funded", "amount": "25",
            "currency": "USDT", "network": "tron",
        }})
    )
    body = {f: "x" for f in PAYOUT_LINK_FIELDS}
    make_sync().payout_links.create(**body)
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
def test_payment_link_all_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payment/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"link_id": "l1", "url": "u"}})
    )
    body = {f: "x" for f in PAYMENT_LINK_FIELDS}
    make_sync().payment_links.create(**body)
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
def test_split_rule_all_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/split/rule").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"rule_id": "r1", "percent": 10}})
    )
    body = {f: "x" for f in SPLIT_RULE_FIELDS}
    make_sync().splits.create_rule(**body)
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
def test_split_helpers_still_work():
    """Обёртки ``split_to_*`` строят тело сами — они не должны спотыкаться о проверку."""
    route = respx.post(f"{BASE}/v1/split/rule").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {"rule_id": "r1", "percent": 10}})
    )
    client = make_sync()
    client.splits.split_to_address(address="T...", network="tron", percent=10, note="партнёр А")
    client.splits.split_to_merchant(merchant_id="m2", percent=5)
    assert json.loads(route.calls[0].request.content) == {
        "address": "T...", "network": "tron", "percent": 10, "note": "партнёр А"
    }
    assert json.loads(route.calls[1].request.content) == {"merchant_id": "m2", "percent": 5}


# ─────────────────────────────── Async ───────────────────────────────


@respx.mock
async def test_async_payment_typo_raises_before_request():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=_payment_ok())
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await client.payments.create(amont="10", currency="USD", order_id="o1")
    assert "'amont'" in str(ei.value) and "'amount'" in str(ei.value)
    assert route.call_count == 0


@respx.mock
async def test_async_payout_typo_raises():
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await client.payouts.create(amount="5", currency="USDT", adress="T...", order_id="w1")
    assert "'adress'" in str(ei.value)


@respx.mock
async def test_async_payout_link_typo_raises():
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await client.payout_links.create(currency="USDT", network="tron", amout="25")
    assert "'amout'" in str(ei.value)


@respx.mock
async def test_async_payment_link_typo_raises():
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await client.payment_links.create(amount_mode="fixed", currency="USD", expires="60")
    assert "'expires'" in str(ei.value)


@respx.mock
async def test_async_split_rule_typo_raises():
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await client.splits.create_rule(address="T...", network="tron", percnt=10)
    assert "'percnt'" in str(ei.value)


@respx.mock
async def test_async_payment_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payment").mock(return_value=_payment_ok())
    body = {f: "x" for f in PAYMENT_FIELDS}
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        await client.payments.create(**body)
    assert json.loads(route.calls[0].request.content) == body


@respx.mock
async def test_async_payout_link_known_fields_pass_through():
    route = respx.post(f"{BASE}/v1/payout/link").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "link_id": "l1", "status": "funded", "amount": "25",
            "currency": "USDT", "network": "tron",
        }})
    )
    body = {f: "x" for f in PAYOUT_LINK_FIELDS}
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        await client.payout_links.create(**body)
    assert json.loads(route.calls[0].request.content) == body


# ──────────────── Полнота покрытия: ни один create-метод не забыт ────────────────

#: Все денежные create-методы SDK и их белые списки. Список ведётся руками намеренно:
#: добавили новый create-метод — добавьте сюда, и тест заставит навесить на него проверку.
CREATE_METHODS = [
    ("payments.create", "payments", "create", PAYMENT_FIELDS),
    ("payouts.create", "payouts", "create", PAYOUT_FIELDS),
    ("payout_links.create", "payout_links", "create", PAYOUT_LINK_FIELDS),
    ("payment_links.create", "payment_links", "create", PAYMENT_LINK_FIELDS),
    ("splits.create_rule", "splits", "create_rule", SPLIT_RULE_FIELDS),
]


def _assert_message(msg, label, fields):
    """Сообщение должно назвать метод, само неизвестное поле и все допустимые имена."""
    assert label in msg, "сообщение называет метод"
    assert "'definitely_not_a_field'" in msg, "сообщение называет неизвестное поле"
    assert "Допустимые поля" in msg, "сообщение перечисляет допустимые имена"
    for f in fields:
        assert f in msg, f"в списке допустимых полей нет {f!r}"


@pytest.mark.parametrize("label,group,method,fields", CREATE_METHODS)
def test_every_sync_create_method_checks_params(label, group, method, fields):
    """Каждый create-метод СИНХРОННОГО клиента отбивает неизвестное поле — и называет допустимые.

    Проверка идёт до подписи и до сети, поэтому HTTP здесь не мокается: пропусти метод
    неизвестное имя дальше — тест упал бы на реальной попытке соединения, а не на TypeError.
    """
    client = make_sync()
    with pytest.raises(TypeError) as ei:
        getattr(getattr(client, group), method)(definitely_not_a_field="x")
    _assert_message(str(ei.value), label, fields)


@pytest.mark.parametrize("label,group,method,fields", CREATE_METHODS)
async def test_every_async_create_method_checks_params(label, group, method, fields):
    """То же для АСИНХРОННОГО клиента.

    Нюанс: у async-методов проверка живёт в теле корутины, поэтому ``TypeError`` прилетает
    на ``await``, а не в момент вызова. Запрос всё равно не уходит — до подписи дело не доходит.
    """
    async with AsyncOblodaiClient(public_id="p", secret="s", base_url=BASE, retry=None) as client:
        with pytest.raises(TypeError) as ei:
            await getattr(getattr(client, group), method)(definitely_not_a_field="x")
    _assert_message(str(ei.value), label, fields)


@pytest.mark.parametrize("label,group,method,fields", CREATE_METHODS)
def test_create_whitelists_are_sane(label, group, method, fields):
    """Белый список непустой, и все имена — snake_case-строки, как в JSON-тегах ядра.

    Сами наборы сверены со структурами запросов в ``services/core/internal/app/payapi``:
    ``PaymentRequest``, ``PayoutRequest``, ``PayoutLinkItem``, ``PaymentLinkCreateRequest``,
    ``SplitRuleRequest``.
    """
    assert fields, f"белый список {label} пуст"
    for field in fields:
        assert isinstance(field, str)
        assert field == field.strip().lower()
        assert " " not in field
