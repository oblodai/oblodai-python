# Oblodai Python SDK

Официальный Python SDK для платёжного шлюза **Oblodai**: приём платежей, выплаты, массовые
операции (батчи), платёжные и payout-ссылки, сплиты, счета на e-mail, статические кошельки,
вебхуки. Синхронный и асинхронный клиенты, подпись запросов, разбор ответов в pydantic-модели,
типизированные ошибки и автоматические повторы.

> **v1.1.0 — ломающее изменение идемпотентности.** SDK больше **не подставляет** `order_id`.
> От дублей при повторах защищает заголовок `Idempotency-Key`, который SDK генерирует сам
> (один раз на вызов). Подробнее — в разделе «Повторы (retry) и идемпотентность».

> **Базовый URL.** По умолчанию — `https://api.oblodai.com`. При необходимости переопределите `base_url` и свои ключи при инициализации.

## Установка

```bash
pip install oblodai
```

Требуется Python 3.9+. Зависимости: `httpx`, `pydantic>=2`.

## Учётные данные

Рекомендуется хранить ключи в переменных окружения (см. `.env.example`), а не в коде:

```bash
export OBLODAI_PUBLIC_ID=oblodai_...
export OBLODAI_SECRET=oblodai_live_...
# необязательно:
export OBLODAI_BASE_URL=https://api.oblodai.com
```

```python
from oblodai import OblodaiClient

client = OblodaiClient.from_env()   # читает OBLODAI_PUBLIC_ID / OBLODAI_SECRET / OBLODAI_BASE_URL
```

## Быстрый старт (синхронно)

```python
from oblodai import OblodaiClient

# либо явно (эквивалент from_env выше):
client = OblodaiClient(
    public_id="oblodai_...",
    secret="oblodai_live_...",
    base_url="https://api.oblodai.com",  # укажите реальный
)

payment = client.payments.create(
    amount="10",
    currency="USD",
    order_id="order-1",
    to_currency="USDT",
    network="tron",
)

print(payment.address)  # адрес для оплаты
print(payment.url)      # hosted-страница оплаты
```

## Асинхронно

```python
import asyncio
from oblodai import AsyncOblodaiClient

async def main():
    async with AsyncOblodaiClient(public_id="...", secret="...") as client:
        payment = await client.payments.create(
            amount="10", currency="USD", order_id="order-1",
            to_currency="USDT", network="tron",
        )
        print(payment.address)

asyncio.run(main())
```

Синхронный клиент тоже поддерживает контекст-менеджер (`with OblodaiClient(...) as client:`).

## Проверка вебхуков

Подпись вебхука отличается от подписи запроса — SDK делает и то, и другое. Для входящих вебхуков
берите **сырое тело** и заголовки `X-Webhook-Timestamp` / `X-Webhook-Signature`.

```python
from flask import Flask, request
from oblodai import construct_event, OblodaiSignatureError

app = Flask(__name__)
WEBHOOK_SECRET = "b7c1e9..."  # из client.webhooks.register()

@app.post("/oblodai/callback")
def callback():
    raw = request.get_data()  # СЫРОЕ тело — не пересериализовывать

    # Пробные тела (is_test) не подписаны
    import json
    if json.loads(raw).get("is_test"):
        return "ok", 200

    try:
        event = construct_event(
            WEBHOOK_SECRET,
            raw,
            request.headers,          # проверит подпись И свежесть (replay-защита)
        )
    except OblodaiSignatureError:
        return "bad signature", 403

    if event["type"] == "payment" and event["status"] == "paid":
        # пометить заказ event["order_id"] оплаченным (идемпотентно по uuid + status)
        pass
    return "ok", 200
```

`construct_event` и `verify_webhook` по умолчанию проверяют свежесть в окне 5 минут
(`max_age_seconds=300`). Передайте `max_age_seconds=0`, чтобы отключить.

## Обработка ошибок

Все ошибки API — экземпляры `OblodaiAPIError` с машиночитаемым `.code`. Ветвитесь по коду.

```python
from oblodai import OblodaiAPIError

try:
    client.payouts.create(
        amount="25", currency="USDT", network="tron",
        address="T...", order_id="payout-1",
    )
except OblodaiAPIError as e:
    if e.code == "payout.insufficient_funds":
        ...  # недостаточно средств
    elif e.code == "payout.funds_maturing":
        ...  # средства ещё дозревают — временно, e.is_retriable == True
    print(e.code, e.status, e.message)
```

### Классы ошибок

| Класс | Когда |
|---|---|
| `OblodaiAPIError` | API вернул конверт `error`. Есть `.code`, `.status`, `.is_retriable`. |
| `OblodaiConnectionError` | Сеть недоступна. |
| `OblodaiTimeoutError` | Истёк таймаут запроса. |
| `OblodaiSignatureError` | Не прошла проверка подписи вебхука. |
| `OblodaiError` | Базовый класс для всех выше. |

## Повторы (retry) и идемпотентность

Временные ошибки (`5xx`, `429`, сетевые сбои) повторяются автоматически с
экспоненциальным backoff и джиттером (на `429` соблюдается `Retry-After`). Ошибки запроса
(`4xx`) не повторяются. `payout.funds_maturing` — терминальная ошибка (средства ещё зреют)
и НЕ повторяется автоматически.

```python
from oblodai import OblodaiClient, RetryConfig

client = OblodaiClient(
    public_id="...", secret="...",
    retry=RetryConfig(max_attempts=4, initial_delay=0.5, max_delay=30.0),
    # retry=None — отключить
)
```

**Как устроена защита от дублей (v1.1.0).** На создающих вызовах (`payments.create`,
`payments.refund`, `payments.resolve`, `payouts.create`, `payouts.create_mass`, все
`create_batch`, `account.transfer_to_personal`) SDK генерирует заголовок `Idempotency-Key`
(uuid4) **один раз до цикла ретраев** — все внутренние повторы уходят с одним и тем же ключом,
поэтому таймаут/обрыв сети не создаст дубль счёта или перевода. В подпись запроса заголовок не
входит.

```python
# свой ключ идемпотентности — уйдёт в ЗАГОЛОВОК, в тело запроса не попадает
client.payments.create(amount="10", currency="USD", order_id="ord-1",
                       idempotency_key="my-op-42")
```

- **`order_id` уходит как есть** — SDK его больше не подставляет и не переписывает
  (в v1.0.x при пустом `order_id` подставлялся `idem-<uuid>`). Это ваш бизнес-идентификатор:
  задавайте его явно и сохраняйте ДО вызова, чтобы потом найти платёж через `payments.info`.
- **Выплаты:** `order_id` обязателен всегда (требование API).
- **Payout-ссылки (`payout_links.*`)** заголовок не используют — там дедупликация через
  per-link `reference` (см. ниже).

## Новое в v1.1.0

### Массовые операции (батчи)

До 5000 платежей/возвратов/выплат одним подписанным запросом (одна отметка rate-limit).
Обработка в фоне: постановка возвращает `batch_id`, результаты — через `batches.info`.

```python
sub = client.payments.create_batch([
    {"amount": "10", "currency": "USD", "order_id": "a-1"},
    {"amount": "20", "currency": "EUR", "order_id": "a-2"},
], on_error="continue")   # "continue" (по умолчанию) или "stop"

info = client.batches.info(sub.batch_id, limit=100)
if info.done:                       # status == "completed"
    print(info.succeeded, info.failed)
    for item in info.items:
        print(item.idx, item.status, item.result or item.error)

client.refunds.create_batch([{"uuid": "p1", "reference": "r-1", "amount": "5"}])
client.payouts.create_batch([{"amount": "5", "currency": "USDT", "network": "tron",
                              "address": "T...", "order_id": "w-1"}])
```

Ключи дедупликации внутри пачки: у платежей/выплат обязателен `order_id` на каждом элементе,
у возвратов — `reference` + `uuid`/`order_id` инвойса.

### Платёжные ссылки

Переиспользуемая ссылка: по ней платят много людей, каждый платёж — свой инвойс.

```python
link = client.payment_links.create(amount_mode="open", currency="USD", title="Донат")
print(link.url)

client.payment_links.list(limit=50)
client.payment_links.info(link.link_id)          # + платежи по ссылке
client.payment_links.toggle(link.link_id, active=False)

# публичные (без подписи) — то, что зовёт ваша страница оплаты
client.payment_links.public_get(link.link_id)
client.payment_links.checkout(link.link_id, amount="10", currency="USD", network="tron")
```

`client.links` — синоним `client.payment_links`.

### Payout-ссылки («крипто-чеки»)

Резервируете сумму, не зная кошелька получателя; получатель открывает `claim_url`
и сам вводит адрес. Требуется PAYOUT/API-ключ.

```python
link = client.payout_links.create(
    currency="USDT", network="tron", amount="25",
    reference="bonus-42",        # ключ дедупликации (Idempotency-Key здесь не используется)
    expires_in_hours=720,        # задавайте ЯВНО: при 0/отсутствии срок клампится к 1 часу
    email="user@example.com",    # опционально: письмо с кнопкой «Получить средства»
)
print(link.claim_url)            # claim_token/claim_url возвращаются ТОЛЬКО здесь — сохраните

client.payout_links.create_batch([{...}, ...])   # до 500 ссылок, общий batch_id
client.payout_links.list(limit=50)
client.payout_links.info(link.link_id)           # после claim: payout_id, claim_address
client.payout_links.cancel(link.link_id)         # только funded → возврат резерва

# публичные (без подписи) — для своей страницы claim
client.payout_links.claim_info(token)                    # GET /v1/claim/{token}
client.payout_links.claim(token, address="T...", memo=None)
```

### Сплиты

Доля каждого входящего платежа автоматически уходит партнёру.

```python
client.splits.split_to_address(address="T...", network="tron", percent=10, note="партнёр А")
client.splits.split_to_merchant(merchant_id="m2", percent=5)     # обратимо при возвратах
client.splits.list_rules()
client.splits.delete_rule(rule_id)
client.splits.get_config() / client.splits.set_config(refund_hold_hours=24)
```

### Счёт на e-mail и resolve недоплаты

```python
client.payments.send_email(uuid=payment.uuid, email="buyer@example.com")

# платёж в статусе wrong_amount (недоплата): оставить себе или вернуть плательщику
client.payments.resolve(uuid=payment.uuid, action="accept")
client.payments.resolve(uuid=payment.uuid, action="refund")   # address по умолчанию — адрес плательщика
```

## Обзор методов

```python
# Платежи
client.payments.create(amount=..., currency=..., order_id=..., ...)
client.payments.create_batch([...], on_error="continue")
client.payments.info(order_id="order-1")
client.payments.history(limit=25, offset=0, status="paid")
client.payments.services()
client.payments.qr(order_id="order-1")
client.payments.resend(order_id="order-1")
client.payments.refund(order_id="order-1", amount="10")   # address опционален (кроме UTXO)
client.payments.refund_batch([...])                        # = client.refunds.create_batch
client.payments.resolve(uuid=..., action="accept" | "refund")
client.payments.send_email(uuid=..., email=...)
client.payments.set_accepted([...]) / list_accepted()
client.payments.set_discount(...) / list_discounts()
client.payments.set_accuracy(...) / get_accuracy()
client.payments.set_autorefund(...) / get_autorefund()

# Возвраты пачкой
client.refunds.create_batch([...], on_error="continue")

# Выплаты
client.payouts.create(amount=..., currency=..., address=..., order_id=...)
client.payouts.create_mass([...])
client.payouts.create_batch([...], on_error="continue")
client.payouts.info(order_id="payout-1")
client.payouts.history(...)
client.payouts.services()
client.payouts.calculate(...)
client.payouts.approve(uuid)
client.payouts.refund(...)
client.payouts.get_fee_config() / set_fee_config(bool)
client.payouts.get_refund_fee_config() / set_refund_fee_config(bool)

# Пачки
client.batches.info(batch_id, limit=100, offset=0)

# Платёжные ссылки (client.links — синоним)
client.payment_links.create(...) / list() / info(link_id) / toggle(link_id, active)
client.payment_links.public_get(link_id) / checkout(link_id, ...)   # публичные, без подписи

# Payout-ссылки (крипто-чеки)
client.payout_links.create(...) / create_batch([...]) / list() / info(link_id) / cancel(link_id)
client.payout_links.claim_info(token) / claim(token, address=...)   # публичные, без подписи

# Сплиты
client.splits.create_rule(...) / split_to_address(...) / split_to_merchant(...)
client.splits.list_rules() / delete_rule(rule_id) / get_config() / set_config(refund_hold_hours=...)

# Кошельки
client.wallets.create(currency="USDT", network="tron", order_id="client-42")
client.wallets.block(address="T...")
client.wallets.blocked_address_refund(uuid="...", address="T...")
client.wallets.qr("T...")

# Аккаунт
client.account.balance()
client.account.referral()
client.account.transfer_to_personal(amount="50", currency="USDT")
client.account.vrcs(enabled=True)

# Вебхуки
client.webhooks.register("https://...")
client.webhooks.deliveries()
client.webhooks.test_payment(url_callback="https://...")

# Настройки
client.settings.list_auto_withdraw() / set_auto_withdraw(...) / delete_auto_withdraw(currency)
client.settings.list_allowlist() / add_allowlist(cidr) / remove_allowlist(cidr) / enable_allowlist(bool)

# Курсы (публично, без ключа)
client.rates.list("ETH")
```

Асинхронный клиент имеет те же методы — с `await`.

## Замечания

- **Суммы — строки** в единицах валюты (`"25.00"`), не числа. Так сохраняется точность.
- **`order_id` — ваш бизнес-идентификатор**, по которому вы находите платёж через
  `payments.info`. С v1.1.0 SDK его НЕ подставляет: от дублей защищает заголовок
  `Idempotency-Key` (автоматически или через kwarg `idempotency_key`). Для выплат `order_id`
  обязателен.
- **Секрет — только на сервере.** SDK серверный; не встраивайте ключ в клиентские приложения.
  Исключение — публичные методы (`payout_links.claim*`, `payment_links.public_get/checkout`,
  `rates.*`): они не подписываются и ключей не требуют.
- **Модели игнорируют неописанные поля** — дополнительные поля в ответе API не сломают разбор.

## Лицензия

MIT
