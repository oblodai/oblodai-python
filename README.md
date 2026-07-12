# Oblodai Python SDK

Официальный Python SDK для платёжного шлюза **Oblodai**: приём платежей, выплаты, статические
кошельки, вебхуки. Синхронный и асинхронный клиенты, подпись запросов, разбор ответов в
pydantic-модели, типизированные ошибки и автоматические повторы.

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

## Повторы (retry)

Временные ошибки (`5xx`, `429`, сетевые сбои) повторяются автоматически с
экспоненциальным backoff и джиттером. Ошибки запроса (`4xx`) не повторяются.
`payout.funds_maturing` — терминальная ошибка (средства ещё зреют) и НЕ повторяется автоматически.

```python
from oblodai import OblodaiClient, RetryConfig

client = OblodaiClient(
    public_id="...", secret="...",
    retry=RetryConfig(max_attempts=4, initial_delay=0.5, max_delay=30.0),
    # retry=None — отключить
)
```

> **Важно про таймаут.** Таймаут не означает, что операция не прошла. Благодаря идемпотентности по
> `order_id` повтор безопасен: если выплата уже создана — вернётся она же, дубля не будет.
> Для `payments.create` и `account.transfer_to_personal` SDK сам подставляет стабильный `order_id`
> (`idem-<uuid>`), если вы его не задали, так что все попытки ретрая используют один ключ и дубль
> не возникает. Для выплат задавайте `order_id` явно.

## Обзор методов

```python
# Платежи
client.payments.create(amount=..., currency=..., order_id=..., ...)
client.payments.info(order_id="order-1")
client.payments.history(limit=25, offset=0, status="paid")
client.payments.services()
client.payments.qr(order_id="order-1")
client.payments.resend(order_id="order-1")
client.payments.refund(order_id="order-1", address="T...", amount="10")
client.payments.set_accepted([...]) / list_accepted()
client.payments.set_discount(...) / list_discounts()
client.payments.set_accuracy(...) / get_accuracy()
client.payments.set_autorefund(...) / get_autorefund()

# Выплаты
client.payouts.create(amount=..., currency=..., address=..., order_id=...)
client.payouts.create_mass([...])
client.payouts.info(order_id="payout-1")
client.payouts.history(...)
client.payouts.services()
client.payouts.calculate(...)
client.payouts.approve(uuid)
client.payouts.refund(...)
client.payouts.get_fee_config() / set_fee_config(bool)
client.payouts.get_refund_fee_config() / set_refund_fee_config(bool)

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
- **`order_id`/`reference` — ваш ключ идемпотентности.** Задавайте всегда для платежей и выплат.
  Если не задан, для `payments.create` и `account.transfer_to_personal` SDK подставит его сам
  (`idem-<uuid>`); для выплат укажите свой, чтобы связать операцию со своим заказом.
- **Секрет — только на сервере.** SDK серверный; не встраивайте ключ в клиентские приложения.
- **Модели игнорируют неописанные поля** — дополнительные поля в ответе API не сломают разбор.

## Лицензия

MIT
