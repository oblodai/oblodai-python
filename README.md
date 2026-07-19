# Oblodai Python SDK

Официальный Python SDK для платёжного шлюза **Oblodai**: приём платежей, выплаты, массовые
операции (батчи), платёжные и payout-ссылки, сплиты, счета на e-mail, статические кошельки,
вебхуки, песочница разработчика. Синхронный и асинхронный клиенты, подпись запросов, разбор ответов в pydantic-модели,
типизированные ошибки и автоматические повторы.

> **v1.1.0 — ломающее изменение идемпотентности.** SDK больше **не подставляет** `order_id`.
> От дублей при повторах защищает заголовок `Idempotency-Key`, который SDK генерирует сам
> (один раз на вызов). Подробнее — в разделе «Повторы (retry) и идемпотентность».

> **Базовый URL — только `https://`.** По умолчанию — `https://api.oblodai.com`; при
> необходимости переопределите `base_url` при инициализации. Схема `http://` **отклоняется**
> (`ValueError` при создании клиента): по ней заголовок подписи `X-Signature` уходит открытым
> текстом и его может перехватить любой посредник. **Исключение — локальные стенды на петлевом
> хосте:** `localhost`, `127.0.0.1`, `::1` (например `http://localhost:8095`) работают по `http`,
> потому что такой трафик не покидает машину.

## Установка

```bash
pip install oblodai
```

Требуется Python 3.9+. Зависимости: `httpx`, `pydantic>=2`.

## Где взять ключи

Ключи выдаются в **личном кабинете Oblodai** — [oblodai.com](https://oblodai.com), раздел
API-ключей. Пара состоит из:

* **public id** — идентификатор ключа, уходит в заголовке `X-Public-Id`;
* **секрет** — им подписывается каждый запрос (`X-Signature`). Секрет **показывается один раз,
  при создании ключа**, и в кабинете больше не отображается. Не сохранили — выпустите новый.

Для разработки берите **тестовый (sandbox) ключ**: public id вида `test_…`, секрет вида
`oblodai_test_…`. Он ходит в те же эндпоинты, но деньги не двигает — см. раздел
[«Песочница / тестирование»](#песочница--тестирование-v120) сразу после быстрого старта;
начинать интеграцию лучше с него. Боевой ключ отличается только значениями — код тот же.

## Учётные данные

Рекомендуется хранить ключи в переменных окружения (см. `.env.example`), а не в коде:

```bash
export OBLODAI_PUBLIC_ID=test_...           # боевой — без префикса test_
export OBLODAI_SECRET=oblodai_test_...      # боевой — oblodai_live_...
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
    public_id="test_...",
    secret="oblodai_test_...",
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

Здесь подставлен **тестовый** ключ (`test_…` / `oblodai_test_…`). Тот же код работает с боевым
ключом — меняется только ключ.

> **Про `payment.url` (и `claim_url` у payout-ссылок).** Эти ссылки собирает шлюз из своего
> публичного базового URL. В проде он обязателен (без него шлюз не стартует), но на **локальном
> стенде** без `GATEWAY_PUBLIC_BASE_URL` оба поля приходят **пустой строкой**. Это не ошибка SDK
> и не ошибка шлюза. Если гоняете локально — собирайте ссылку сами из `payment.uuid`
> (или `claim_token` для payout-ссылки) либо поднимайте свою страницу оплаты на публичных
> эндпоинтах (см. «Свой (кастомный) checkout»).

## Песочница / тестирование (v1.2.0)

У шлюза есть песочница разработчика с **тестовыми ключами**: public id с префиксом `test_`,
секрет с префиксом `oblodai_test_`. **Бизнес-эндпоинты не меняются** и с тестовым ключом
работают ровно так же — интеграционный код одинаков для теста и прода, между ними меняется
ТОЛЬКО ключ:

```bash
# тест
export OBLODAI_PUBLIC_ID=test_...
export OBLODAI_SECRET=oblodai_test_...
# прод — тот же код, другой ключ
export OBLODAI_PUBLIC_ID=oblodai_...
export OBLODAI_SECRET=oblodai_live_...
```

Хелпер `is_test_key(public_id)` возвращает `True` для тестового ключа (префикс `test_`).

Новое — группа `client.sandbox`: пять test-only эндпоинтов, которые заменяют действия
покупателя («покупатель оплатил он-чейн» и т. п.). **Только для тестового кода** — в проде
этих эндпоинтов нет, живой ключ получает HTTP 403 `sandbox.live_key`. Не зовите
`client.sandbox.*` из продакшн-кода.

```python
from oblodai import OblodaiClient

client = OblodaiClient(public_id="test_...", secret="oblodai_test_...")

# 1. Обычный бизнес-код: создаём инвойс
payment = client.payments.create(amount="10", currency="USD", order_id="t-1",
                                 to_currency="USDT", network="tron")

# 2. Вместо покупателя «платим он-чейн»
client.sandbox.simulate_deposit(invoice_id=payment.uuid)   # ровно причитающееся, сразу подтверждено

# 3. Обычный бизнес-код: убеждаемся, что инвойс оплачен
assert client.payments.info(uuid=payment.uuid).payment_status == "paid"

# 4. Кран тестового баланса (≤ 1000000 за вызов) — и гоняем выплату
client.sandbox.faucet(asset="USDT", amount="1000")
client.payouts.create(amount="25", currency="USDT", network="tron",
                      address="T...", order_id="w-1")
```

Остальные методы группы:

```python
# недоплата / переплата / депозит «в пути»
# amount задаётся в валюте оплаты инвойса (pay_amount); меньше причитающегося — недоплата,
# больше — переплата (paid_over). Не задан — платится ровно причитающееся.
client.sandbox.simulate_deposit(invoice_id=..., amount="5")   # частичная оплата
# → payment_status станет "wrong_amount_waiting", а НЕ "wrong_amount": счёт ещё жив и ждёт
#   доплату. resolve здесь ответит 409 resolution.not_underpaid. В "wrong_amount" счёт перейдёт
#   только после истечения lifetime (минимум 300 с) — создавайте инвойс с коротким lifetime,
#   если хотите дождаться этого перехода в тесте.
client.sandbox.simulate_deposit(invoice_id=..., confirmations=1,      # приходит неподтверждённым
                                txid="tx-1")
client.sandbox.simulate_deposit(invoice_id=..., confirmations=20,     # повтор с ТЕМ ЖЕ txid
                                txid="tx-1")                          # углубляет подтверждения

client.sandbox.reset()               # см. ниже: НЕ «чистый лист»

# инспектор вебхуков: list → берём .id → replay(delivery_id=<этот .id>)
deliveries = client.sandbox.list_webhooks()   # до 50, новые первыми, с полем payload
d = deliveries[0]
print(d.id, d.event_type, d.status, d.payload)
res = client.sandbox.replay_webhook(d.id)     # ИМЕННО d.id — это и есть delivery_id
assert res.delivery_id == d.id and res.requeued
```

Про имена в этой связке: в выдаче `list_webhooks()` идентификатор доставки лежит в поле
**`.id`** (`SandboxDelivery.id`), а `replay_webhook` принимает его позиционно как
**`delivery_id`** (так называется поле в теле `POST /v1/sandbox/webhooks/replay`, и оно же
возвращается в ответе `SandboxReplayResult.delivery_id`). Это одно и то же значение — uuid
доставки; разные имена по краям — просто разные роли одного идентификатора.

Нюансы:

- **`sandbox.reset()` — это не «чистый лист».** Он отменяет инвойсы **только** в статусах
  `created` и `select` и обнуляет балансы (компенсирующей проводкой — журнал append-only,
  история экспериментов остаётся читаемой). Инвойс, по которому уже **виден депозит**
  (`confirm_check`, `wrong_amount_waiting`), reset **сознательно не трогает**: отмена дала бы
  депозиту подтвердиться в отменённый счёт и зачислить деньги без события. Это решение шлюза,
  а не недоделка. В ответе — `invoices_cancelled` и `balances_zeroed`: если после reset тест
  видит «лишний» инвойс, сверьтесь с этими числами, а не считайте reset сломанным. Если тесту
  нужна полная изоляция — заводите новый инвойс с новым `order_id`, а не рассчитывайте на reset.
- **«Мелкие» депозиты сами НЕ дозревают.** Депозит с `confirmations` меньше требуемого
  оставляет инвойс в `confirm_check` **навсегда**: песочница не переэмитит транзакцию и
  ничего не досчитает в фоне. Единственный способ довести инвойс до `paid` — повторить
  `simulate_deposit` с **тем же `txid`** и бОльшим `confirmations`.
- **~10 минут — это про другое.** Это maturity-**холд на выплате**: свежепришедшие средства
  какое-то время нельзя выводить, и `payouts.create` до истечения холда падает с
  `payout.funds_maturing`. Холд снимается фоновым джобом по возрасту средств
  (в песочнице — 10 минут по умолчанию, настраивается на стороне шлюза). К глубине
  подтверждений инвойса этот таймер отношения не имеет.
- **UTXO-сети (Bitcoin и т. п.)** ведут себя как в проде: авто-возврата переплаты нет
  и адрес плательщика неизвестен — для возврата нужен явный `address`
  (см. `payments.refund` / `payments.resolve`).
- `sandbox.list_webhooks` — единственный **подписанный GET** в SDK: подпись считается по
  той же канонической строке с пустым телом (`{ts}\nGET\n/v1/sandbox/webhooks\n`).


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

## Статусы

### Платёж (`payment.payment_status`)

| Статус | Что означает | Терминальный |
| --- | --- | --- |
| `check` | счёт создан, оплаты ещё не видели | нет |
| `select` | валюто-агностичный счёт: покупатель ещё не выбрал валюту/сеть (см. `payments.public_select`) | нет |
| `confirm_check` | оплата увидена, ждём подтверждений сети | нет |
| `wrong_amount_waiting` | увидели **частичную** оплату, ждём доплату — счёт ещё жив | нет |
| `wrong_amount` | счёт **закрылся** недоплаченным | да |
| `paid` | оплачен полностью (в пределах допуска `accuracy_payment_percent`) | да |
| `paid_over` | переплачен; излишек уходит в авто-возврат, если он включён и сеть его поддерживает | да |
| `cancel` | истёк или отменён | да |

В ответе есть булево поле `is_final` — используйте его, а не собственный список статусов.

**`wrong_amount_waiting` и `wrong_amount` — разные вещи, и путать их дорого.** Пока счёт не
истёк, частичная оплата держит его в `wrong_amount_waiting`: покупатель ещё может доплатить,
и тогда счёт станет `paid`. В `wrong_amount` он переходит только после истечения срока жизни
(`lifetime`, минимум 300 с). `payments.resolve` работает **только** с `wrong_amount`; на
`wrong_amount_waiting` шлюз отвечает `409 resolution.not_underpaid`.

### Выплата (`payout.status`)

| Статус | Что означает |
| --- | --- |
| `check` | создана, ждёт одобрения (`payouts.approve`) |
| `process` | одобрена: уходит или уже ушла в сеть |
| `paid` | подтверждена сетью |
| `fail` | не удалась |
| `cancel` | отменена |

## Проверка вебхуков

Подпись вебхука отличается от подписи запроса — SDK делает и то, и другое. Для входящих вебхуков
берите **сырое тело** и заголовки `X-Webhook-Timestamp` / `X-Webhook-Signature`.

> **Секрет вебхука — НЕ секрет API-ключа.** Проверять подпись нужно тем секретом, который
> вернул `client.webhooks.register(url)` (поле `.secret`) — это отдельный секрет **эндпоинта**.
> Если подставить сюда `OBLODAI_SECRET` (секрет API-ключа), проверка не пройдёт **ни на одном**
> вебхуке. Сохраните `register().secret` при регистрации: заново он не выдаётся.

> **`register()` — это upsert ЕДИНСТВЕННОГО эндпоинта на проект, а не «добавить ещё один».**
> Повторный вызов с ДРУГИМ URL не создаёт второй эндпоинт: возвращается **тот же**
> `endpoint_id`, доставки переезжают на новый URL, а старый молча замолкает. Секрет при этом
> **сохраняется** намеренно — уже поставленные в очередь доставки подписаны им, и смена секрета
> осиротила бы их (401 → ретраи → dead-letter → потерянные события `paid`/выплат). Отсюда
> практическое следствие: чтобы вести несколько получателей, разводите их **проектами**
> (по ключу на проект), а не повторными `register()`.

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
        ...  # средства ещё дозревают: e.is_retriable == False — сами не повторяем,
             # ждём снятия холда и вызываем позже (см. «Повторы (retry) и идемпотентность»)
    print(e.code, e.status, e.message)
```

### Проверка имён полей

Create-методы принимают поля как `**kwargs` и отправляют их в тело подписанного запроса.
Раньше опечатка в имени **не вызывала ошибки**: шлюз (как любой разборщик JSON) неизвестные
ключи игнорирует — и денежная операция тихо исполнялась с другим смыслом. `amout="1"` вместо
`amount="1"` создавал счёт не на ту сумму, `expires_in_hour` вместо `expires_in_hours` давал
payout-ссылке срок жизни 1 час, `percnt` вместо `percent` обнулял долю партнёра. Ответ во всех
случаях выглядел успешным.

Теперь имена сверяются с белым списком полей, которые поддерживает сам шлюз, **до** подписи и
отправки; неизвестное имя — `TypeError` с подсказкой:

```python
client.payments.create(amont="10", currency="USD", order_id="o-1")
# TypeError: payments.create(): неизвестное поле: 'amont'. Возможно, имелось в виду: 'amount'.
#            Допустимые поля: accuracy_payment_percent, additional_data, amount, currency, ...
```

Проверяются **все** денежные create-методы: `payments.create`, `payouts.create`,
`payout_links.create`, `payment_links.create`, `splits.create_rule` — в синхронном и асинхронном
клиентах одинаково. (У async-методов проверка живёт в теле корутины, поэтому `TypeError`
прилетает на `await`, а не в момент вызова; запрос всё равно не уходит.)
Списки полей — в `oblodai._params` (`PAYMENT_FIELDS`, `PAYOUT_FIELDS`, `PAYOUT_LINK_FIELDS`,
`PAYMENT_LINK_FIELDS`, `SPLIT_RULE_FIELDS`). Известные поля работают ровно как раньше: список
описывает то, что шлюз и так принимает, — это не новые ограничения, а отказ молчать об опечатке.
Ошибка — `TypeError`, а не `OblodaiAPIError`: до API дело не доходит, запрос не отправляется.

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
`create_batch`, `account.transfer_to_personal`, `payout_links.create`,
`payout_links.create_batch`, `wallets.blocked_address_refund`) SDK генерирует заголовок `Idempotency-Key`
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
- **Payout-ссылки (`payout_links.create` / `create_batch`)** резервируют деньги, поэтому с
  v1.2.0 тоже уходят с `Idempotency-Key`, и шлюз его **уважает**: повтор с тем же ключом
  реплеит первый ответ (та же ссылка, тот же `claim_token`, в ответе `Idempotent-Replayed:
  true`), а баланс дебетуется **ровно один раз**. Без заголовка два одинаковых вызова
  создадут ДВЕ ссылки. Per-link `reference` остаётся вторым, durable слоем защиты — он
  работает и без заголовка, и когда ответ батча слишком велик для кэша (см. ниже).
- **`wallets.blocked_address_refund`** защищён иначе и сильнее: шлюз сам строит
  детерминированный reference `refund-wallet:<wallet_id>`, берёт per-wallet advisory-lock и
  внутри лока возвращает уже созданную выплату. Повтор — в том числе параллельный и вообще
  без заголовков — отдаёт ТУ ЖЕ выплату, вторая не создаётся. Оговорка: повтор с ДРУГИМ
  `address` вернёт первую выплату на ПЕРВЫЙ адрес (адрес в reference не входит).
- **`payouts.approve`** заголовка не требует: это переход состояния, принимается только
  `pending`, иначе 409 `payout.not_pending`. Читайте этот 409 как «уже одобрено», а не как
  сбой, и уточняйте статус через `payouts.info`.

### Коды ответов идемпотентности (payout-ссылки)

| Код | HTTP | Когда | Ретраится SDK |
|---|---|---|---|
| `idempotency.key_reused` | 400 | тот же ключ с ДРУГИМ телом запроса | нет |
| `idempotency.bad_key` | 400 | ключ длиннее 255 символов | нет |
| `idempotency.in_progress` | 409 | параллельный повтор, пока первый ещё выполняется | нет |
| `idempotency.unavailable` | 503 | стор идемпотентности недоступен (fail-closed by design) | **да** |
| `payoutlink.duplicate_reference` | 409 | `reference` уже занят (раньше отдавался 500) | нет |

Классификация в SDK (`OblodaiAPIError.is_retriable`) этому соответствует: `4xx` (включая
оба 409 и оба 400) — терминальные, `5xx`/`429` — временные. Смена 500 → 409 на дубле
`reference` важна именно поэтому: раньше SDK крутил бесполезные ретраи, теперь ошибка
сразу возвращается вызывающему.

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

client.payments.refund_batch([{"uuid": "p1", "reference": "r-1", "amount": "5"}])
client.payouts.create_batch([{"amount": "5", "currency": "USDT", "network": "tron",
                              "address": "T...", "order_id": "w-1"}])
```

Ключи дедупликации внутри пачки: у платежей/выплат обязателен `order_id` на каждом элементе,
у возвратов — `reference` + `uuid`/`order_id` инвойса.

> **`client.refunds` устарела.** Раньше возвраты пачкой предлагались как
> `client.refunds.create_batch(...)`. Это **то же самое**, что `client.payments.refund_batch(...)`:
> один эндпоинт `POST /v1/refund/batch`, одно тело, одна идемпотентность — просто два имени
> одной операции. При этом группа `refunds` есть **только в Python SDK** (в TS, Go, Rust и PHP
> возвраты пачкой живут на платежах), так что код с ней не переносится между языками.
> **Ничего не удалено:** `client.refunds.create_batch(...)` работает как раньше, но обращение к
> `client.refunds` выдаёт `DeprecationWarning`; удаление планируется в 2.0. Канонический путь —
> **`client.payments.refund_batch(...)`**.
>
> ```python
> # было
> client.refunds.create_batch([...])        # DeprecationWarning
> # стало
> client.payments.refund_batch([...])       # канон, тот же эндпоинт и тот же результат
> ```
>
> Предупреждения `DeprecationWarning` Python по умолчанию скрывает вне `__main__` — чтобы увидеть
> его в своём коде, запустите интерпретатор с `-W default::DeprecationWarning` (в pytest они
> видны из коробки).

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

**Как называется этот ресурс.** Канон — **`client.payment_links`**; именно это имя используется
во всех SDK Oblodai (`paymentLinks` в JS и PHP, `payment_links` в Python и Rust, `PaymentLinks`
в Go), поэтому код с ним переносится между языками без переименований. **`client.links` —
документированный синоним** того же объекта: он никуда не денется, но в новом коде лучше писать
`payment_links`.

```python
client.links is client.payment_links   # True — один и тот же объект
```

### Payout-ссылки («крипто-чеки»)

Резервируете сумму, не зная кошелька получателя; получатель открывает `claim_url`
и сам вводит адрес. Требуется PAYOUT/API-ключ.

```python
link = client.payout_links.create(
    currency="USDT", network="tron", amount="25",
    reference="bonus-42",        # durable-дедуп между вызовами; внутренние ретраи закрыты
                                 # заголовком Idempotency-Key, который шлюз уважает
    expires_in_hours=720,        # задавайте ЯВНО: при 0/отсутствии срок клампится к 1 часу
    email="user@example.com",    # опционально: письмо с кнопкой «Получить средства»
)
print(link.claim_token)          # claim_token/claim_url возвращаются ТОЛЬКО здесь — сохраните
print(link.claim_url)            # локально без GATEWAY_PUBLIC_BASE_URL это ПУСТАЯ строка

client.payout_links.create_batch([{...}, ...])   # до 500 ссылок, общий batch_id
client.payout_links.list(limit=50)
client.payout_links.info(link.link_id)           # после claim: payout_id, claim_address
client.payout_links.cancel(link.link_id)         # только funded → возврат резерва

# публичные (без подписи) — для своей страницы claim
client.payout_links.claim_info(token)                    # GET /v1/claim/{token}
client.payout_links.claim(token, address="T...", memo=None)
```

**Батчи ссылок — ставьте `reference` на каждый item.** Ответ размером больше 256 КБ шлюз
не кэширует, и тогда повтор с тем же `Idempotency-Key` выполнится ЗАНОВО; уникальный
`reference` — тот слой, который в этом случае всё равно отобьёт дубль (409
`payoutlink.duplicate_reference`). Ещё одна особенность: частично упавшая пачка реплеится
КАК ЕСТЬ — упавшие элементы под тем же ключом не переисполняются, отправьте их НОВЫМ ключом.

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

# resolve работает ТОЛЬКО для счёта, который ЗАКРЫЛСЯ недоплаченным (payment_status ==
# "wrong_amount"). Пока счёт жив и ждёт доплату (wrong_amount_waiting) — 409 resolution.not_underpaid.
info = client.payments.info(uuid=payment.uuid)
if info.payment_status == "wrong_amount":
    client.payments.resolve(uuid=payment.uuid, action="accept")   # оставить частичную оплату себе
    # либо вернуть плательщику (address по умолчанию — записанный payer_address):
    # client.payments.resolve(uuid=payment.uuid, action="refund")
```

**Недоплата проходит два состояния, и resolve доступен только во втором.** Пока не истёк
`lifetime` счёта, частичная оплата держит его в `wrong_amount_waiting` — покупатель ещё может
доплатить. `wrong_amount` наступает, когда счёт закрылся недоплаченным; вот тогда и появляется
выбор accept/refund. Вызов `resolve` в первом состоянии — `409 resolution.not_underpaid`
(в сообщении ошибки шлюз возвращает фактический статус). Подробнее — в разделе «Статусы».

`action="accept"` дополнительно глушит авто-возврат недоплаты, а `action="refund"` требует
PAYOUT/API-ключ. Оба идемпотентны по заголовку `Idempotency-Key` (свой — kwarg
`idempotency_key`); у `refund` есть ещё per-refund ключ `reference`.

## Внутренние переводы (v1.2.0)

Перевод БЕЗ комиссии с баланса мерчанта на личный кошелёк **пользователя платформы**
(деньги не уходят он-чейн — это внутренняя проводка). `to_user_id` — id пользователя
платформы (UUID-строка), **НЕ username**: username резолвится в id через публичный
профиль кабинета. Требуется PAYOUT/API-ключ.

```python
res = client.account.transfer_to_user(
    to_user_id="5c3f6a1e-...",     # UUID пользователя платформы
    amount="50", currency="USDT",
    order_id="salary-2026-07",     # опционально — ваш бизнес-идентификатор
)
print(res.recipient_balance)       # новый баланс получателя

# зарплатная пачка (до 5000 переводов) — обработка в фоне
sub = client.account.transfer_batch(
    [
        {"to_user_id": "5c3f6a1e-...", "amount": "50", "currency": "USDT"},
        {"to_user_id": "9d1e2b4c-...", "amount": "70", "currency": "USDT"},
    ],
    on_error="continue",
)
info = client.batches.info(sub.batch_id)   # прогресс и по-элементные результаты
```

Идемпотентность — та же лестница, что у остальных денежных эндпоинтов: заголовок
`Idempotency-Key` (SDK шлёт авто-uuid4, стабильный между ретраями; свой — kwarg
`idempotency_key`), иначе шлюз берёт `order_id`, иначе — подпись запроса.

## Свой (кастомный) checkout (v1.2.0)

Публичные (без подписи и без ключа) эндпоинты инвойса — чтобы собрать **свою страницу
оплаты** вместо hosted-страницы шлюза: показать адрес/QR/сумму, дать покупателю выбрать
валюту и опрашивать статус прямо из браузера.

```python
# состояние инвойса (без секрета мерчанта — можно звать из браузера)
state = client.payments.public_get(payment.uuid)          # GET /v1/pay/{id}
print(state.payment_status, state.address, state.amount_remaining)

# валюто-агностичный инвойс (payment_status == "select"): покупатель выбирает метод
for m in state.accepted or []:                            # методы на выбор
    print(m.currency, m.network)
finalized = client.payments.public_select(payment.uuid,   # POST /v1/pay/{id}/select
                                          currency="USDT", network="tron")
print(finalized.address, finalized.payer_amount)          # курс зафиксирован, адрес выделен
```

`public_get` возвращает только покупательские поля (без `additional_data` и
`payer_email`); `public_select` фиксирует курс, выделяет депозитный адрес и переводит
инвойс из `select` в `created`. Та же публичная семья, что `payment_links.public_get` /
`checkout` и `payout_links.claim*`.

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
client.payments.refund_batch([...])                        # канон (client.refunds — устарело)
client.payments.resolve(uuid=..., action="accept" | "refund")
client.payments.send_email(uuid=..., email=...)
client.payments.set_accepted([...]) / list_accepted()
client.payments.set_discount(...) / list_discounts()
client.payments.set_accuracy(...) / get_accuracy()
client.payments.set_autorefund(...) / get_autorefund()
client.payments.public_get(payment_id)                     # публично, без подписи — свой checkout
client.payments.public_select(payment_id, currency=..., network=...)   # публично, без подписи

# Возвраты пачкой — канон payments.refund_batch (см. выше про client.refunds)
client.payments.refund_batch([...], on_error="continue")

# Выплаты
client.payouts.create(amount=..., currency=..., address=..., order_id=...)
client.payouts.create_mass([...])
client.payouts.create_batch([...], on_error="continue")
client.payouts.info(order_id="payout-1")
client.payouts.history(...)
client.payouts.services()
client.payouts.calculate(...)
client.payouts.approve(uuid)                     # повтор → 409 payout.not_pending = «уже одобрено»
client.payouts.refund(...)
client.payouts.get_fee_config() / set_fee_config(bool)
client.payouts.get_refund_fee_config() / set_refund_fee_config(bool)

# Пачки
client.batches.info(batch_id, limit=100, offset=0)

# Платёжные ссылки (канон payment_links; client.links — документированный синоним)
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
client.wallets.blocked_address_refund(uuid="...", address="T...")   # once-only на шлюзе: повтор
                                                                    # вернёт ТУ ЖЕ выплату
client.wallets.qr("T...")

# Аккаунт
client.account.balance()
client.account.referral()
client.account.transfer_to_personal(amount="50", currency="USDT")
client.account.transfer_to_user(to_user_id="...", amount="50", currency="USDT")  # UUID, не username
client.account.transfer_batch([...], on_error="continue")  # результаты — batches.info(batch_id)
client.account.vrcs(enabled=True)

# Вебхуки
client.webhooks.register("https://...")   # UPSERT единственного эндпоинта проекта:
                                         # .secret — секрет ДЛЯ ПРОВЕРКИ ПОДПИСИ вебхуков
client.webhooks.deliveries()
client.webhooks.test_payment(url_callback="https://...")

# Настройки
client.settings.list_auto_withdraw() / set_auto_withdraw(...) / delete_auto_withdraw(currency)
client.settings.list_allowlist() / add_allowlist(cidr) / remove_allowlist(cidr) / enable_allowlist(bool)

# Курсы (публично, без ключа)
client.rates.list("ETH")

# Песочница (ТОЛЬКО тестовый ключ test_… — см. раздел выше)
client.sandbox.simulate_deposit(invoice_id=..., amount=None, confirmations=None, txid=None)
client.sandbox.faucet(asset="USDT", amount="1000")
client.sandbox.reset()                        # только инвойсы created/select + обнуление балансов
client.sandbox.list_webhooks()                # → [SandboxDelivery], идентификатор в поле .id
client.sandbox.replay_webhook(d.id)           # .id из list_webhooks() и есть delivery_id
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
  `payments.public_get/public_select`, `rates.*`): они не подписываются и ключей не требуют.
- **Модели игнорируют неописанные поля** — дополнительные поля в ответе API не сломают разбор.
- **Имена полей create-методов проверяются.** Опечатка в имени поля — `TypeError` до
  отправки запроса, а не молча изменённая денежная операция. См. «Проверка имён полей».

## Лицензия

MIT
