# Changelog

Значимые изменения этого пакета. Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — [SemVer](https://semver.org/lang/ru/).

## [1.2.0] — 2026-07-19

### Добавлено
- **Песочница разработчика — группа `client.sandbox`** (sync и async). Работает ТОЛЬКО
  с тестовыми ключами (`test_…` / `oblodai_test_…`); бизнес-эндпоинты с тестовым ключом
  не меняются — между тестом и продом меняется только ключ. Живой ключ на sandbox-эндпоинтах
  получает HTTP 403 `sandbox.live_key`. Только для тестового кода. Методы:
  - `sandbox.simulate_deposit(invoice_id=, amount=, confirmations=, txid=)` —
    `POST /v1/sandbox/deposit`: имитация он-чейн депозита; без `amount` платится ровно
    причитающееся, малое `confirmations` даёт «неподтверждённый» депозит, повтор с тем же
    `txid` и бОльшим числом подтверждений углубляет его.
  - `sandbox.faucet(asset=, amount=, idempotency_key=)` — `POST /v1/sandbox/faucet`:
    тестовый баланс (≤ 1000000 за вызов); `idempotency_key` здесь — поле ТЕЛА запроса
    (контракт эндпоинта), не заголовок.
  - `sandbox.reset()` — `POST /v1/sandbox/reset`: отмена открытых инвойсов и обнуление
    балансов (история сохраняется).
  - `sandbox.list_webhooks()` — `GET /v1/sandbox/webhooks`: последние доставки вебхуков
    (до 50, новые первыми), с `payload`.
  - `sandbox.replay_webhook(delivery_id)` — `POST /v1/sandbox/webhooks/replay`.
- **Подписанный GET.** Транспорт теперь умеет подписывать GET-запросы: та же каноническая
  строка `{ts}\nGET\n{path}\n` с пустым телом (используется `sandbox.list_webhooks`).
- **Хелпер `is_test_key(public_id)`** — `True`, если ключ тестовый (префикс `test_`).
- Новые pydantic-модели: `SandboxDeposit`, `SandboxFaucetResult`, `SandboxResetResult`,
  `SandboxDelivery` (с `payload`), `SandboxReplayResult`.
- **Внутренние переводы пользователю платформы** (sync и async, PAYOUT/API-ключ):
  - `account.transfer_to_user(to_user_id=, amount=, currency=, order_id=)` —
    `POST /v1/transfer/to-user`: перевод БЕЗ комиссии с баланса мерчанта на личный
    кошелёк пользователя платформы. `to_user_id` — id пользователя (UUID-строка),
    НЕ username. Идемпотентность — лестница как у прочих денежных эндпоинтов:
    заголовок `Idempotency-Key` (авто-uuid4, стабилен между ретраями; свой —
    `idempotency_key`), иначе `order_id`, иначе подпись запроса. Модель ответа —
    `TransferToUserResult` (`currency`, `amount`, `to_user_id`, `recipient_balance`).
  - `account.transfer_batch([...], on_error=)` — `POST /v1/transfer/batch`:
    зарплатная пачка переводов to-user (до 5000); результаты — через
    `batches.info(batch_id)`.
- **Публичные эндпоинты инвойса для кастомного checkout** (sync и async, без подписи
  и без ключа — можно звать из браузера):
  - `payments.public_get(payment_id)` — `GET /v1/pay/{id}`: покупательское состояние
    инвойса (адрес, сумма, QR, статус, срок); для валюто-агностичного инвойса
    в статусе `select` дополнительно приходит `accepted` — методы на выбор
    (новое поле `Payment.accepted`).
  - `payments.public_select(payment_id, currency=, network=)` —
    `POST /v1/pay/{id}/select`: покупатель выбирает валюту+сеть; фиксирует курс,
    выделяет депозитный адрес, переводит инвойс из `select` в `created`.
    Ответ — обычная модель `Payment`.

## [1.1.0] — 2026-07-15

Требует обновлённого шлюза (заголовок `Idempotency-Key`). Не публикуйте/не обновляйтесь до его деплоя.

### ЛОМАЮЩЕЕ: идемпотентность через заголовок `Idempotency-Key`
- SDK **больше НЕ подставляет** `order_id` (`idem-<uuid>` из v1.0.1/v1.0.2). Если вы полагались
  на автоподстановку — теперь `order_id` в платеже будет отсутствовать; задавайте его явно.
- От дублей при повторах защищает заголовок **`Idempotency-Key`**: генерируется (uuid4) один
  раз на вызов **до цикла ретраев** и одинаков во всех внутренних повторах. В подпись запроса
  заголовок не входит. Шлётся на создающих вызовах: `payments.create`, `payments.refund`
  (и `payouts.refund`), `payments.resolve`, `payments.create_batch`, `refunds.create_batch`,
  `payouts.create`, `payouts.create_mass`, `payouts.create_batch`,
  `account.transfer_to_personal`.
- Свой ключ — kwarg `idempotency_key` в этих методах: уходит в заголовок, в тело запроса
  не попадает.
- `order_id` уходит **как есть** (без нормализации пробелов) — это ваш бизнес-идентификатор.
- Исключение: `payout_links.*` (`/v1/payout/link*`) заголовок не используют — дедупликация
  через per-link `reference`.

### Добавлено
- **Батчи:** `payments.create_batch`, `refunds.create_batch` (новая группа `client.refunds`;
  синоним `payments.refund_batch`), `payouts.create_batch` — до 5000 элементов, `on_error`
  `"continue"`/`"stop"`; `batches.info(batch_id, limit=, offset=)` с моделью `BatchInfo`
  (`info.done`, по-элементные `result`/`error`).
- **Платёжные ссылки:** `payment_links.create/list/info/toggle` + публичные (без подписи)
  `public_get` и `checkout`. `client.links` — синоним группы.
- **Payout-ссылки («крипто-чеки»):** `payout_links.create/create_batch(до 500)/list/info/cancel`
  + публичные `claim_info(token)` (`GET /v1/claim/{token}`) и `claim(token, address=, memo=)` —
  оба без подписи. `claim_token`/`claim_url` возвращаются только из `create`.
- **Сплиты:** `splits.create_rule/list_rules/delete_rule/get_config/set_config` + обёртки
  `split_to_address`/`split_to_merchant`.
- **Счёт на e-mail:** `payments.send_email(uuid=|order_id=, email=)`.
- **Resolve недоплаты:** `payments.resolve(uuid=|order_id=, action="accept"|"refund")` для
  платежей в статусе `wrong_amount`.
- Новые pydantic-модели: `BatchSubmitResult`, `BatchInfo`, `BatchItem`, `PaymentLink*`,
  `SplitRule*`, `PayoutLink*`, `PaymentResolution`; поля платежа `payer_address`,
  `refund_status`, `refunds[]`.

### Изменено
- `address` в `payments.refund` больше не обязателен — по умолчанию возврат уходит на адрес
  плательщика (для UTXO-сетей адрес по-прежнему нужен).

## [1.0.2] — 2026-07-12

### Исправлено
- **Нормализация «пустого» `order_id` для авто-идемпотентности.** `payments.create` и
  `account.transfer_to_personal` теперь подставляют `idem-<uuid>` не только когда `order_id`
  отсутствует/`None`/`""`, но и когда это строка из одних пробелов (`"   "`). Пустой после
  `.strip()` ключ не даёт дедупликации на бэкенде, поэтому такой `order_id` считается
  отсутствующим. Реальные значения сохраняются без изменений.

## [1.0.1] — 2026-07-12

### Исправлено
- **Безопасность денег: авто-идемпотентность.** `payments.create` и `account.transfer_to_personal`
  (sync и async) теперь подставляют стабильный `order_id` (`idem-<uuid>`), если он не задан. Клиент
  переподписывает каждую попытку ретрая, а бэкенд дедуплицирует по `order_id` — без ключа повтор
  после таймаута/5xx мог создать дубль платежа/перевода. Выплаты не затронуты.
- **`Retry-After` больше не зажимается до `max_delay`.** Указание сервера (например `Retry-After: 60`)
  теперь соблюдается; действует лишь абсолютный потолок 300с.
- **`payout.funds_maturing` стала терминальной** и больше не повторяется автоматически.
- **Вебхуки: не-ASCII в заголовке подписи** больше не приводит к `TypeError` из
  `hmac.compare_digest`, а даёт штатную `OblodaiSignatureError` (fail-closed).

## [1.0.0] — 2026-07-12

### Добавлено
- Первый релиз официального Python SDK для платёжного шлюза Oblodai.
- Приём платежей, выплаты и массовые выплаты, статические кошельки, возвраты, вебхуки,
  публичные справочники (курсы валют, каталог монет и сетей).
- Подпись запросов HMAC-SHA256 и проверка подписи вебхуков (сравнение в постоянном времени,
  защита от replay).
- Конструктор из переменных окружения `OblodaiClient.from_env()` — `OBLODAI_PUBLIC_ID` / `OBLODAI_SECRET` /
  `OBLODAI_BASE_URL`.
- Автоматические повторы с экспоненциальным backoff и учётом заголовка `Retry-After` на 429.
