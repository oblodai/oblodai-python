<div align="center">

<a href="https://oblodai.com">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-white.svg">
    <img src="https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-black.svg" alt="oblodai" height="52">
  </picture>
</a>

<h3>Официальный Python SDK для платёжного шлюза <a href="https://oblodai.com">oblodai</a></h3>

Платежи, выплаты, платёжные ссылки, сплиты, статические кошельки, вебхуки — один API-ключ.

<a href="https://pypi.org/project/oblodai/"><img src="https://img.shields.io/pypi/v/oblodai?style=flat-square&label=PyPI" alt="PyPI"></a>
<a href="https://github.com/oblodai/oblodai-python/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/oblodai/oblodai-python/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
<img src="https://img.shields.io/pypi/pyversions/oblodai?style=flat-square" alt="Python versions">
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-000000?style=flat-square" alt="License: MIT"></a>

[Documentation](https://docs.oblodai.com) · [Dashboard](https://my.oblodai.com) · [Read in English →](README.md)

</div>

---

Официальный Python SDK для платёжного шлюза **Oblodai**: приём платежей, выплаты, массовые операции
(батчи), платёжные ссылки, выплатные ссылки (крипточеки), сплиты, статические кошельки, переводы,
вебхуки. Подпись запросов, разбор ответов, типизированные ошибки, идемпотентность и ретраи — из
коробки.

Python ≥ 3.9, одна зависимость времени выполнения (`httpx`), синхронный **и** асинхронный клиенты,
сквозная типизация из собственного снимка контракта шлюза: у каждого маршрута, который шлюз
предоставляет (120), здесь есть метод, а у каждого запроса и ответа — `TypedDict`.

> **Базовый URL.** По умолчанию `https://api.oblodai.com`. При необходимости переопределите
> `base_url` и передайте свои ключи при инициализации. Схема должна быть `https://`; обычный
> `http://` допускается только для локальной петли (`http://127.0.0.1:8095`) либо с явной опцией
> небезопасного режима (`allow_insecure_base_url=True` или `OBLODAI_ALLOW_INSECURE=1`).

## Установка

```bash
pip install oblodai
```

Нужен Python 3.9 или новее (в CI проверяются 3.9 – 3.13). Единственная зависимость времени
выполнения — `httpx` (`>=0.24,<1.0`); верхняя граница поставлена намеренно: в httpx 1.0 может
измениться API стриминга и таймаутов, которым SDK управляет напрямую.

Пишете код вместе с ИИ-агентом? Дайте ему [AGENTS.md](AGENTS.md) — этот файл едет и внутри
установленного пакета, по пути `importlib.resources.files("oblodai") / "AGENTS.md"`. Переходите с
1.2? [MIGRATION-1.3.md](MIGRATION-1.3.md): это переписывание, а не обновление.

## Где взять ключи

У мерчанта **один API-ключ**. Он выдаётся в [кабинете](https://my.oblodai.com), раздел
**API keys**, как пара «публичный идентификатор + секрет», и подписывает все маршруты этого SDK —
и приём денег, и вывод:

| учётные данные | как задаётся | для чего |
| -------------- | ------------ | -------- |
| **API-ключ** | `public_id` / `secret` (`OBLODAI_PUBLIC_ID`, `OBLODAI_SECRET`) | все подписанные маршруты: `payments.*`, `payouts.*`, `refunds.*`, `payment_links.*`, `payout_links.*`, `transfers.*`, `splits.*`, `wallets.*`, `batches.info`, `documents.*`, `settings.*`, `account.*`, `webhooks.*`, `sandbox.*` |
| **токен администратора** | `admin_token` (`OBLODAI_ADMIN_TOKEN`) | только заведение магазинов на self-hosted-шлюзе: `merchants.create`, `merchants.create_sandbox` |

Маршрутам для плательщика учётные данные не нужны вовсе: `catalog.currencies`,
`catalog.exchange_rates`, `payments.public_view/select/public_qr`,
`payment_links.public_view/checkout`, `payout_links.claim_preview/claim` и
`documents.download` (ссылка уже подписана).

**Песочница и боевой контур.** Ключ песочницы выдаётся к копии шлюза без блокчейна и узнаётся по
префиксу `test_` (`test_oblodai_…` / `oblodai_test_…`); у боевого ключа такого префикса нет.
Вызывать `sandbox.*` может только ключ `test_`.

**Подключение мерчанта.** `merchants.create` и `merchants.create_sandbox` заводят магазин и
возвращают единственный `api_key`, которым он подписывает вызовы. Они не подписываются и передают
`X-Admin-Token` из `admin_token` (или `OBLODAI_ADMIN_TOKEN`) — это токен администратора на
self-hosted-шлюзе, а не ключ мерчанта.

**Старые раздельные пары.** У магазина, заведённого задолго до 1.3, может остаться пара
`oblodai_pk_…` / `oblodai_wk_…`; шлюз по-прежнему различает их по виду, и вызов не тем ключом даёт
403 `merchant.wrong_key_kind` — единственный случай, когда этот код ещё встречается. Выпустите
актуальный ключ, и различия не станет.

## Быстрый старт

```python
from oblodai import Oblodai

oblodai = Oblodai()  # or Oblodai(public_id="...", secret="...")

invoice = oblodai.payments.create(
    {
        "amount": "25",  # amounts are decimal strings, never floats
        "currency": "USDT",  # what you price in — a fiat (USD, EUR, …) or a crypto asset
        "network": "tron",  # omit to let the payer choose the network on the pay page
        "order_id": "order-1001",  # your reference; idempotent per order_id
        "url_callback": "https://shop.example/oblodai/webhook",
    }
)
print(invoice["url"], invoice["address"], invoice["status"])  # "created"
```

Вывод денег устроен зеркально и подписывается тем же ключом:

```python
payout = oblodai.payouts.create(
    {
        "amount": "10",
        "currency": "USDT",
        "network": "tron",
        "address": "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx",
        "order_id": "payout-1001",
    },
    idempotency_key="payout-1001",  # yours, so a process restart cannot pay twice
)
print(payout["uuid"], payout["status"])  # "pending"
```

Цена в фиате: `{"amount": "25", "currency": "USD", "to_currency": "USDT"}` — `currency` это то, в чём
вы выставляете счёт, `to_currency` — актив, которым платит плательщик. Готовые скрипты лежат в
[`examples/`](examples).

Закрывайте клиент, когда он больше не нужен, или используйте его как контекстный менеджер:

```python
with Oblodai() as oblodai:
    invoice = oblodai.payments.create({"amount": "25", "currency": "USDT"})
```

### Запросы и ответы — обычные словари

Тела запросов передаются словарями с теми же именами полей в `snake_case`, что и на проводе, и
результаты возвращаются так же — ничего не переименовывается, никаких объектов-обёрток заучивать не
нужно. Имена не приходится угадывать: у каждого тела есть `TypedDict` в `oblodai.contract.requests`,
у каждого ответа — `TypedDict` в `oblodai.contract.models`, и оба сгенерированы из контракта шлюза,
поэтому редактор подсказывает поля, а `mypy` ловит опечатку до того, как она уедет в API.

```python
from decimal import Decimal

from oblodai import PaymentRequest

invoice = oblodai.payments.create(amount="25", currency="USDT")
invoice = oblodai.payments.create(PaymentRequest(amount=Decimal("25"), currency="USDT"))
```

### Асинхронный клиент

```python
import asyncio
from oblodai.aio import AsyncOblodai


async def main() -> None:
    async with AsyncOblodai() as oblodai:
        invoice = await oblodai.payments.create({"amount": "25", "currency": "USDT"})
        async for payment in await oblodai.payments.list_history(limit=50):
            print(payment.uuid)


asyncio.run(main())
```

У обоих клиентов одно и то же чистое ядро: подпись, разбор конверта, решение о ретрае и правила
идемпотентности — это код без ввода-вывода, который приводят в движение и синхронный, и асинхронный
транспорт, поэтому разойтись они не могут.

### Суммы

Суммы — десятичные строки в собственном масштабе актива. Никогда не применяйте к ним `float()`:
`float` в теле запроса — `ConfigError` (`sdk.float_amount`) до отправки. `Decimal` можно — он уходит
точной строкой, и хелперы его тоже принимают:

```python
from decimal import Decimal

from oblodai import add_amounts, amount_equals, compare_amounts

add_amounts("10.000000", "0.5")  # "10.500000"
compare_amounts("25", "25.0000")  # 0
amount_equals("25", "25.000000")  # True
add_amounts(Decimal("1.10"), "2.20")  # "3.30"
```

Точно так же нельзя сравнивать их через `<` или `sorted()`: строки сравниваются лексикографически, и
`"10" < "9"` даёт `True`. Всё, что не является десятичной строкой, вызывает `AmountError` (он же
`ValueError`).

## Песочница и тестирование

Ключ песочницы работает с копией шлюза без блокчейна: фейковый баланс из крана, симулированные
депозиты вместо блоков и настоящие подписанные вебхуки. Интегрируйтесь сначала с ней — здесь ничего
не касается блокчейна.

```python
oblodai.sandbox.faucet({"asset": "USDT", "amount": "100"})  # test funds, out of thin air
oblodai.sandbox.deposit(
    {"invoice_id": invoice["uuid"], "amount": "25", "confirmations": 20, "txid": "demo-tx-1"}
)
for delivery in oblodai.sandbox.webhooks(limit=5):  # the delivery log, payloads included
    print(delivery["event_type"], delivery["status"])
oblodai.sandbox.replay(delivery_id)  # re-send a terminal (delivered/dead) delivery
oblodai.sandbox.reset()  # cancel open invoices, zero the balances
```

Повторите `sandbox.deposit` с тем же `txid`, чтобы добавить подтверждений. Тестовые доставки — из
`webhooks.test(kind, …)` и из песочницы — подписаны ровно так же, как боевые, и несут `test: true` в
теле (а также заголовок `X-Webhook-Test: true`): проверяйте `delivery.is_test` (или
`webhooks.is_test_event(event)`) и никогда не считайте такую доставку движением денег.
[`examples/sandbox.py`](examples/sandbox.py) проходит весь денежный путь примерно за секунду.

## Обзор методов

Шестнадцать неймспейсов покрывают все 120 маршрутов шлюза.

| Неймспейс | Методы | Маршруты |
| --------- | ------ | -------- |
| `payments` | `cancel` `create` `get_aml_links` `get_checkout_config` `get_info` `get_qr` `list_history` `list_services` `resolve` `send_email` `set_checkout_config` | `/v1/payment/cancel` `/v1/payment` `/v1/payment/aml-links` `/v1/checkout-config/get` `/v1/payment/info` `/v1/payment/qr` `/v1/payment/history` `/v1/payment/services` `/v1/payment/resolve` `/v1/payment/send-email` `/v1/checkout-config/set` |
| `payment_links` | `create` `get` `list` `toggle` | `/v1/payment/link` `/v1/payment/link/info` `/v1/payment/link/list` `/v1/payment/link/toggle` |
| `refunds` | `blocked_wallet` `payment` | `/v1/wallet/blocked-address-refund` `/v1/payment/refund` |
| `payouts` | `approve` `calculate` `cancel` `create` `create_mass` `create_transfer_batch` `get_info` `list_history` `list_services` `transfer_to_personal` `transfer_to_user` `validate` | `/v1/payout/approve` `/v1/payout/calculate` `/v1/payout/cancel` `/v1/payout` `/v1/payout/mass` `/v1/transfer/batch` `/v1/payout/info` `/v1/payout/history` `/v1/payout/services` `/v1/transfer/to-personal` `/v1/transfer/to-user` `/v1/payout/validate` |
| `payout_links` | `cancel` `claim_payout` `create` `create_batch` `get` `get_payout_claim` `list` | `/v1/payout/link/cancel` `/v1/claim/{token}` `/v1/payout/link` `/v1/payout/link/batch` `/v1/payout/link/info` `/v1/payout/link/list` |
| `batches` | `create_payment` `create_payout` `create_refund` `get_info` | `/v1/payment/batch` `/v1/payout/batch` `/v1/refund/batch` `/v1/batch/info` |
| `splits` | `create_rule` `delete_rule` `get_config` `get_recipient_opt_in` `list_rules` `set_config` `set_recipient_opt_in` | `/v1/split/rule` `/v1/split/rule/delete` `/v1/split/config/get` `/v1/split/recipient/optin/get` `/v1/split/rule/list` `/v1/split/config/set` `/v1/split/recipient/optin` |
| `wallets` | `block` `create` `get_qr` | `/v1/wallet/block` `/v1/wallet` `/v1/wallet/qr` |
| `account` | `get_balance` `get_summary` `list_exchange_rates` | `/v1/balance` `/v1/summary` `/v1/exchange-rate/list` |
| `webhooks` | `list_deliveries` `register` `requeue_delivery` `resend_payment` `rotate_secret` `send_legacy_test` `send_test_conversion` `send_test_payment` `send_test_payout` `send_test_wallet` `set_active` | `/v1/webhooks/deliveries` `/v1/webhooks` `/v1/webhooks/deliveries/requeue` `/v1/payment/resend` `/v1/webhooks/rotate-secret` `/v1/payment/testing-webhook` `/v1/test-webhook/conversion` `/v1/test-webhook/payment` `/v1/test-webhook/payout` `/v1/test-webhook/wallet` `/v1/webhooks/active` |
| `settings` | `configure_vrcs` `delete_auto_withdraw_rule` `get_accuracy` `get_auto_convert` `get_auto_refund` `get_payment_fee_config` `get_payout_fee_config` `get_refund_fee_config` `list_accepted_currencies` `list_api_log` `list_auto_withdraw_rules` `list_discounts` `set_accepted_currencies` `set_accuracy` `set_auto_convert` `set_auto_refund` `set_auto_withdraw_rule` `set_discount` `set_payment_fee_config` `set_payout_fee_config` `set_refund_fee_config` | `/v1/vrcs` `/v1/auto-withdraw/delete` `/v1/payment/accuracy/get` `/v1/payment/autoconvert/get` `/v1/payment/autorefund/get` `/v1/payment/fee-config/get` `/v1/payout/fee-config/get` `/v1/payout/refund-fee-config/get` `/v1/payment/accepted/list` `/v1/payment/api-log` `/v1/auto-withdraw/list` `/v1/payment/discount/list` `/v1/payment/accepted/set` `/v1/payment/accuracy/set` `/v1/payment/autoconvert/set` `/v1/payment/autorefund/set` `/v1/auto-withdraw/set` `/v1/payment/discount/set` `/v1/payment/fee-config/set` `/v1/payout/fee-config/set` `/v1/payout/refund-fee-config/set` |
| `api_allowlist` | `add_entry` `list` `remove_entry` `set_enabled` | `/v1/api-allowlist/add` `/v1/api-allowlist/list` `/v1/api-allowlist/remove` `/v1/api-allowlist/enable` |
| `referrals` | `get_info` | `/v1/referral/info` |
| `documents` | `create_job` `download_job_file` `get_balance` `get_batch` `get_fees` `get_job` `get_ledger` `get_payment_link` `get_payout_link_cheque` `get_referrals` `get_signed` `get_split` `get_statement` `get_wallet_statement` | `/v1/documents/jobs` `/v1/documents/jobs/file` `/v1/documents/balance` `/v1/documents/batch` `/v1/documents/fees` `/v1/documents/jobs/info` `/v1/documents/ledger` `/v1/documents/link` `/v1/payout/link/cheque` `/v1/documents/referrals` `/v1/documents/{kind}/{id}` `/v1/documents/split` `/v1/documents/statement` `/v1/documents/wallet/statement` |
| `checkout` | `get` `get_onramp` `get_public_payment_link` `get_qr` `get_source_of_funds_form` `list_currencies` `payment_link` `select_method` `start_onramp` `submit_source_of_funds` | `/v1/pay/{id}` `/v1/pay/{id}/onramp` `/v1/link/{id}` `/v1/pay/{id}/qr` `/v1/aml/{token}` `/v1/currencies` `/v1/link/{id}/checkout` `/v1/pay/{id}/select` |
| `sandbox` | `faucet` `list_webhooks` `onboard_store` `replay_webhook` `reset` `simulate_deposit` | `/v1/sandbox/faucet` `/v1/sandbox/webhooks` `/v1/merchants/{id}/sandbox` `/v1/sandbox/webhooks/replay` `/v1/sandbox/reset` `/v1/sandbox/deposit` |

У всех методов один и тот же набор завершающих именованных аргументов (поля
`oblodai.RequestOptions`): `idempotency_key`, `timeout` (секунды, на одну попытку), `max_retries`,
`extra_headers` (дополнительные заголовки только для этого вызова) и `request_id` (уходит в
`X-Request-ID`; если не задан — uuid4). Списочные методы принимают ещё `limit=` /
`offset=`. Всё остальное вызывает `TypeError` до отправки запроса.

Маршруты для плательщика — `payments.public_view/select/public_qr`,
`payment_links.public_view/checkout`, `payout_links.claim_preview/claim` — не требуют учётных данных
вообще. Методы документов возвращают `FileResult(content, content_type, filename)`.

### Списки

Списочные методы возвращают ленивый `Page`. Пока результат не потребляют, он не делает запросов:

```python
page = oblodai.payments.history({"limit": 50}).first()  # one page
page.items, page.total, page.has_pages

for payment in oblodai.payments.history({"limit": 50}):  # every page, fetched on demand
    print(payment["uuid"])

recent = oblodai.payouts.history({"limit": 50}).all(max_items=200)
```

`page.items` и `page.paginate` — сокращения для первой страницы. В асинхронном клиенте тот же объект
либо ожидают (`await client.payments.history()`), либо обходят через `async for`.

### Статусы

- Платёж: `select → created → confirm_check → paid | paid_over | wrong_amount | expired | cancelled`.
  `is_payment_paid` покрывает paid/paid_over; для `wrong_amount` нужен `refunds.resolve({...})`.
- Выплата: `pending → approved → awaiting_cosign → broadcasting → sent → confirmed | failed | cancelled`.

```python
from oblodai import is_payment_paid, is_payout_final
```

## Вебхуки

Эндпоинт регистрируется один раз — секрет возвращается тоже один раз, при регистрации:

```python
endpoint = oblodai.webhooks.register("https://shop.example/oblodai/webhook")
endpoint_secret = endpoint["secret"]  # store it; it is not shown again
```

Проверяйте каждую доставку по **сырым байтам запроса**, а не по повторно сериализованному разбору:

```python
from oblodai import webhooks

delivery = webhooks.verify_delivery(raw_body, request.headers, secret=endpoint_secret)
event = delivery.event  # {"type": "payment"|"payout"|"wallet", ...}
if webhooks.is_stale(event, last_sequence_you_processed):
    return  # a retry that arrived after a newer state
if webhooks.is_known_event(event) and event["type"] == "payment":
    ...  # narrowed to the payment shape
```

Событие, тип которого новее этого SDK, возвращается, а не отвергается: `is_known_event` даёт `False`,
а `event["type"]` содержит исходную строку. Подтверждайте такое событие в любом случае — отказ
заставит шлюз повторять совершенно корректную доставку.

`SignatureError` и `WebhookPayloadError` означают разное: первое — доставка не от шлюза (отвечайте
**401**, и 401 только на провал подписи), второе — подлинная доставка, тело которой этот приёмник не
может использовать (`webhook.bad_payload`; отвечайте **400**, потому что повтор ничего не исправит).
Подпись проверяется раньше окна свежести, поэтому поддельная доставка никогда не узнает, какое время
считает текущим ваш эндпоинт.

Дедуплицируйте по `delivery.id` (`X-Webhook-Id`, стабилен между повторами). Тестовые доставки несут
`delivery.is_test`. Во время ротации секрета (`webhooks.rotate_secret`) передавайте
`previous_secret=` не меньше 26 часов: доставки, поставленные в очередь до ротации, всю свою жизнь
повторов остаются подписанными старым секретом. `tolerance_sec` (по умолчанию 300) ограничивает,
насколько несвежей может быть доставка.

Полноценный приёмник — в [`examples/webhook_receiver.py`](examples/webhook_receiver.py).

## Ошибки

Всё поднимает наследников `OblodaiError`:

```python
from oblodai import OblodaiError, RateLimitError

try:
    oblodai.payouts.create({...})
except RateLimitError as err:
    ...  # err.retry_after
except OblodaiError as err:
    print(err.code, err.http_status, err.retryable, err.request_id, err.field)
```

`str(err)` готов для лога: `[payment.bad_amount] amount must be positive (request_id=rq-9)` (хвост —
только когда id есть); `err.message` остаётся голым текстом.

| класс | HTTP | когда |
| ----- | ---- | ----- |
| `ValidationError` | 400 | некорректный запрос или нарушенное бизнес-правило (`field` укажет поле) |
| `AuthenticationError` | 401 | плохая подпись, неизвестный ключ, расхождение часов, IP вне списка |
| `PermissionDeniedError` | 403 | ключ верный, но не того вида, либо функция отключена |
| `NotFoundError` | 404 | объекта нет |
| `ConflictError` / `IdempotencyConflictError` | 409 | конфликт состояния; тот же ключ с другим телом |
| `RateLimitError` | 429 | слишком много запросов (`retry_after`) |
| `UnavailableError` / `InternalError` | 503 / прочие 5xx | шлюз не смог ответить |
| `TransportError` | — | ответа не было вовсе (`transport.timeout`, `transport.network`, `transport.deadline`) |
| `ConfigError` | — | поднимается до отправки (`sdk.bad_config`, `sdk.bad_header`, `sdk.bad_idempotency_key`, `sdk.idempotency_unsupported`, `sdk.missing_credentials`) |
| `SignatureError` | — | проверка вебхука не прошла — доставка не от шлюза |
| `WebhookPayloadError` | — | подлинная доставка, тело которой непригодно (`webhook.bad_payload`) |
| `ResponseTooLargeError` | — | ответ превысил ограничение по размеру (`sdk.response_too_large`) |
| `AmountError` | — | строка, переданная денежным хелперам, не является десятичной суммой (`sdk.bad_amount`) |

`err.retryable` — это классификация самого шлюза: то, что следовало повторить, SDK уже повторил.
`err.retry_after` — его `Retry-After` в секундах (с потолком в 24 часа), `err.request_id` — то, что
спросит поддержка, `err.synthetic` помечает ответ, пришедший от прокси, а не от API, а
`err.to_dict()` удобно писать в лог: сырого тела там никогда нет.

Ветвитесь по `err.code`, который всегда имеет вид `family.reason`. Коды, которые стоит обрабатывать
по имени: `payout.insufficient_funds` (повторяемый), `payout.funds_maturing` (повторяемый),
`idempotency.key_reused`, `invoice.not_payable`, `payment.not_found`,
`merchant.bad_signature`, `request.rate_limited`. Полный каталог — `oblodai.ERROR_CODES`
(450 codes) — это собственный список шлюза, поэтому код можно сверять точным сравнением, а не
поиском подстроки.

## Ретраи, идемпотентность и таймауты

Можно ли повторить вызов, не угадывается по виду пути: это `ROUTES[key].safe`, собственная
классификация шлюза «только чтение», приезжающая в снимке контракта. Запись, которую шлюз не
дедуплицирует, никогда не отправляется повторно, если она уже могла дойти до шлюза: транспортная
ошибка после того, как запрос ушёл в сокет, может означать, что выплата уже состоялась.

Маршруту создающего типа выдаётся сгенерированный `Idempotency-Key`, переиспользуемый во всех
ретраях этого вызова, так что потерянный ответ не превратится в двойную выплату. Передайте свой
ключ (не длиннее 255 символов), чтобы пережить перезапуск процесса:

```python
oblodai.payouts.create({...}, idempotency_key=f"payout-{order_id}")
```

Передача ключа маршруту, который шлюз не дедуплицирует, вызывает `sdk.idempotency_unsupported`, а не
делает вид, что повтор безопасен, — включая списочные методы, где ключ именно отвергается, а не
молча отбрасывается. Ретраи прекращаются на первом неповторяемом ответе; `Retry-After` всегда важнее
экспоненциальной задержки с джиттером. Настраивается через `RetryOptions(max_retries=…,
base_delay_ms=…)` (по умолчанию: 2 ретрая, база 250 мс, потолок 4 с, потолок учитываемого
`Retry-After` — 30 с); полностью отключается через `RetryOptions(max_retries=0)`.

Ограничения: `timeout` (секунды, одна попытка, по умолчанию 30 с; задаётся и на вызов) и `deadline`
клиента (секунды, весь вызов вместе с ретраями, по умолчанию 90 с); `extra_headers` добавляет
заголовки только этому вызову. Каждый запрос несёт `X-Request-ID` — ваш (`request_id=`) или
сгенерированный uuid4, один на все попытки вызова. Аналога
`AbortSignal` здесь нет: асинхронный вызов отменяется отменой его задачи (`CancelledError`
пробрасывается нетронутым).

Подписанные запросы несут отметку времени, поэтому машина со сбитыми часами не прошла бы
аутентификацию; клиент узнаёт смещение из заголовка `Date` самого шлюза и учитывает его (смещения
больше 24 часов считаются неправдоподобными и игнорируются). Редиректы не выполняются никогда —
подпись действительна только для того URI, для которого она сделана, а подставленный HTTP-клиент,
который всё же пошёл по редиректу, будет пойман и превращён в ошибку. Тела ответов читаются с
ограничением: 8 МиБ для JSON и 64 МиБ для документов; сверх того вызов поднимает
`ResponseTooLargeError`.

### Сырой ответ, `with_options` и хуки

```python
from oblodai import Hooks, Oblodai

oblodai = Oblodai(hooks=Hooks(on_request=print, on_response=print))  # once per attempt
strict = oblodai.with_options(timeout=5, max_retries=0, extra_headers={"X-Tenant": "t1"})
```

`with_options(timeout=, max_retries=, extra_headers=)` возвращает новый клиент на том же HTTP-пуле;
исходный не меняется. `ресурс.with_raw_response.<метод>(...)` возвращает `RawAPIResponse`
(`.status`, `.headers`, `.request_id`, `.parse()` — обычный результат); статус ошибки по-прежнему
бросает исключение. Хуки получают `RequestInfo` перед каждой попыткой (подпись скрыта) и
`ResponseInfo` после неё (`status` 0 и `error`, если ответа не было); вызываются синхронно,
исключение из хука пробрасывается.

## Конфигурация

Каждая опция — именованный аргумент `Oblodai(...)` / `AsyncOblodai(...)`; явный аргумент всегда
важнее переменной окружения.

| опция | по умолчанию | что делает |
| ----- | ------------ | ---------- |
| `public_id`, `secret` | окружение | API-ключ мерчанта |
| `base_url` | `https://api.oblodai.com` | origin API; префикс пути (`https://gw.corp/oblodai`) сохраняется |
| `allow_insecure_base_url` | `False` | разрешает `http://` на не-локальный хост |
| `admin_token` | окружение | `X-Admin-Token` для `merchants.*` на self-hosted-шлюзе |
| `timeout` | `30.0` | секунды на одну попытку; принимается и `httpx.Timeout` (его наибольшая граница) |
| `deadline` | `90.0` | секунды на весь вызов, вместе с ретраями |
| `retry` | `RetryOptions()` | `max_retries`, `base_delay_ms`, `max_delay_ms`, `max_retry_after_ms` |
| `headers` | — | дополнительные заголовки на каждый запрос |
| `logger` | нет | что угодно с `debug/info/warning/error(message, fields)` |
| `http_client` | собственный | ваш `httpx.Client` / `httpx.AsyncClient` |
| `env` | `os.environ` | отображение, из которого клиент читает окружение |

Совсем без аргументов клиент настраивает себя из окружения:

| переменная | что задаёт |
| ---------- | ---------- |
| `OBLODAI_PUBLIC_ID` / `OBLODAI_SECRET` | API-ключ мерчанта |
| `OBLODAI_ADMIN_TOKEN` | открывает `merchants.*` на self-hosted-шлюзе |
| `OBLODAI_BASE_URL` | origin API (по умолчанию `https://api.oblodai.com`; префикс пути сохраняется) |
| `OBLODAI_LOG` | `debug` \| `info` \| `warning` \| `error` — структурные логи в stderr |
| `OBLODAI_ALLOW_INSECURE` | `1` разрешает `http://` на не-локальный хост |

Полный файл с комментариями — [`.env.example`](.env.example); этими шестью переменными окружение
клиента и исчерпывается. Наполовину заданный ключ (`public_id` без своего `secret` или наоборот) —
это `ConfigError` при создании клиента, а не 401 потом.

**Секреты в лог не попадают.** Значения полей, в которых лежит ключ, подпись, пароль чека или ссылка
на получение чека, вычищаются до того, как попадут в логгер, поэтому даже `OBLODAI_LOG=debug` —
который пишет в stderr каждую попытку, её маршрут, статус и тайминг — не сможет их раскрыть. Под
протокол из четырёх методов, которые вызывает транспорт, подходят и `logging.Logger`, и structlog, и
тестовая заглушка.

### Self-hosted или локальный шлюз

```python
Oblodai(base_url="http://127.0.0.1:8095", allow_insecure_base_url=True)
```

Обычный `http://` принимается для локальной петли и без флага; во всех остальных случаях флаг
обязателен, чтобы подпись случайно не ушла с хоста в открытом виде. Заведение мерчанта
(`merchants.*`) не подписывается и передаёт `X-Admin-Token`, когда задан `admin_token`.

## Снимок контракта

`contract/` — он есть в репозитории и в sdist, но не в установленном wheel — содержит собственный
экспорт шлюза: реестр маршрутов, схемы запросов, все перечисления и коды ошибок, векторы для
подписи, эталонные тела ответов по каждому маршруту и настоящие подписанные доставки вебхуков. Он
закреплён за одним коммитом ядра (`CONTRACT_CORE_COMMIT`), и 120 маршрутов и 450 кодов ошибок, которые
предоставляет SDK, — ровно те, что лежат в нём.

```python
from oblodai import CONTRACT_CORE_COMMIT, ROUTES

ROUTES["POST /v1/payout"].auth  # "key" - signed with the merchant's API key
ROUTES["POST /v1/payout"].idempotent  # True
ROUTES["POST /v1/payout"].safe  # False - never re-sent after a transport failure without a key
```

`scripts/codegen.py` превращает снимок в `oblodai/contract/{routes,enums,requests,version}.py`, а
`scripts/gen_async.py` зеркалит слой ресурсов в `oblodai/aio/resources/`. Оба результата проверяет
`scripts/check_drift.py`: он перегенерирует всё во временный каталог и сравнивает, поэтому
закоммиченный код не может разойтись с контрактом — ни в CI, ни локально (`make drift`).

Как обновить: положите свежий экспорт в `contract/`, выполните `make codegen`, затем `make ci`.
Контрактные тесты громко упадут на всём, что изменил снимок, — на новом маршруте, переименованном
поле, переехавшем коде ошибки. В этом и смысл.

## Разработка

```bash
git clone https://github.com/oblodai/oblodai-python && cd oblodai-python
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
make ci            # drift + ruff + mypy + unit and contract tests + packaging
make live          # the same, plus the live tier (needs OBLODAI_LIVE_URL)
make codegen       # regenerate the contract mirror and the async resources
```

Три яруса тестов: `tests/unit` (векторы подписи и вебхуков, правила ретраев, идемпотентности,
поправки часов и разбора URL поверх подставного HTTP-слоя), `tests/contract` (каждый маршрут
подключён к правильному методу, пути, виду ключа и заголовку идемпотентности; каждое эталонное тело
совпадает со своей моделью поле в поле; документация проверяется как код) и `tests/live` (настоящий
шлюз: подключение мерчанта, счёт, депозит, выплата, возврат, ссылки, документы).

Смотрите также [AGENTS.md](AGENTS.md) — сводку для ИИ-агентов, [CHANGELOG.md](CHANGELOG.md) — что
менялось, [MIGRATION-1.3.md](MIGRATION-1.3.md) — переход с 1.2 и [RELEASING.md](RELEASING.md) — как
версия попадает на PyPI.

## Лицензия

MIT — см. [LICENSE](LICENSE).
