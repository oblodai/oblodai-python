<div align="center">

<a href="https://oblodai.com">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-white.svg">
    <img src="https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-black.svg" alt="oblodai" height="52">
  </picture>
</a>

<h3>Official Python SDK for the <a href="https://oblodai.com">oblodai</a> payment gateway</h3>

Payments, payouts, payment links, splits, static wallets, webhooks — one API key.

<a href="https://pypi.org/project/oblodai/"><img src="https://img.shields.io/pypi/v/oblodai?style=flat-square&label=PyPI" alt="PyPI"></a>
<a href="https://github.com/oblodai/oblodai-python/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/oblodai/oblodai-python/ci.yml?branch=main&style=flat-square&label=CI" alt="CI"></a>
<img src="https://img.shields.io/pypi/pyversions/oblodai?style=flat-square" alt="Python versions">
<a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-000000?style=flat-square" alt="License: MIT"></a>

[Documentation](https://docs.oblodai.com) · [Dashboard](https://my.oblodai.com) · [Читать по-русски →](README.ru.md)

</div>

---

The official Python SDK for the **Oblodai** payment gateway: accepting payments, payouts, bulk
operations (batches), payment links, payout links (crypto cheques), splits, static wallets,
transfers, webhooks. Request signing, response parsing, typed errors, idempotency and retries — out
of the box.

Python ≥ 3.9 with a single runtime dependency (`httpx`), a synchronous **and** an asynchronous
client, typed end to end from the gateway's own contract snapshot: every route it exposes (107) has
a method here, and every request and response has a `TypedDict`.

> **Base URL.** Defaults to `https://api.oblodai.com`. Override `base_url` and supply your own keys
> at initialisation if needed. The scheme must be `https://`; plain `http://` is accepted only for
> loopback (`http://127.0.0.1:8095`) or with the explicit allow-insecure option
> (`allow_insecure_base_url=True`, or `OBLODAI_ALLOW_INSECURE=1`).

## Installation

```bash
pip install oblodai
```

Python 3.9 or newer (3.9 – 3.13 are tested in CI). The only runtime dependency is `httpx`
(`>=0.24,<1.0`); the upper bound is deliberate, because httpx 1.0 may move the streaming and
timeout API this SDK drives directly.

Writing code with an AI agent? Point it at [AGENTS.md](AGENTS.md) — it ships inside the installed
package as well, at `importlib.resources.files("oblodai") / "AGENTS.md"`. Coming from 1.2?
[MIGRATION-1.3.md](MIGRATION-1.3.md): it is a rewrite, not an upgrade.

## Where to get keys

A merchant has **one API key**. It is issued in the [dashboard](https://my.oblodai.com) under
**API keys** as a public id and a secret, and it signs every route in this SDK — money-in and
money-out alike:

| credential | configured as | used for |
| ---------- | ------------- | -------- |
| **API key** | `public_id` / `secret` (`OBLODAI_PUBLIC_ID`, `OBLODAI_SECRET`) | every signed route: `payments.*`, `payouts.*`, `refunds.*`, `payment_links.*`, `payout_links.*`, `transfers.*`, `splits.*`, `wallets.*`, `batches.info`, `documents.*`, `settings.*`, `account.*`, `webhooks.*`, `sandbox.*` |
| **admin token** | `admin_token` (`OBLODAI_ADMIN_TOKEN`) | provisioning only, on a self-hosted gateway: `merchants.create`, `merchants.create_sandbox` |

The payer-facing routes need no credentials at all: `catalog.currencies`,
`catalog.exchange_rates`, `payments.public_view/select/public_qr`,
`payment_links.public_view/checkout`, `payout_links.claim_preview/claim` and
`documents.download` (a pre-signed link).

**Sandbox versus live.** A sandbox key is issued against a chainless copy of the gateway and is
recognisable by its `test_` prefix (`test_oblodai_…` / `oblodai_test_…`); a live key carries no such
prefix. Only a `test_` key may call `sandbox.*`.

**Onboarding.** `merchants.create` and `merchants.create_sandbox` provision a store and return the
single `api_key` it signs with. They are unsigned and carry `X-Admin-Token`, taken from
`admin_token` (or `OBLODAI_ADMIN_TOKEN`) — an administrator's token on a self-hosted gateway, not a
merchant key.

**Legacy split pairs.** A store onboarded long before 1.3 may still hold an old
`oblodai_pk_…` / `oblodai_wk_…` pair, which the gateway still gates by kind: using one of those
where the other belongs is the 403 `merchant.wrong_key_kind`, and that is the only case in which
that code can still appear. Issue a current key and the distinction is gone.

## Quick start

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

Money out is the mirror image, signed with the same key:

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

Prices in fiat: `{"amount": "25", "currency": "USD", "to_currency": "USDT"}` — `currency` is what
you charge, `to_currency` the asset the payer sends. Runnable scripts live in
[`examples/`](examples).

Close the client when you are done with it, or use it as a context manager:

```python
with Oblodai() as oblodai:
    invoice = oblodai.payments.create({"amount": "25", "currency": "USDT"})
```

### Requests and responses are plain dicts

Bodies go in as dictionaries with the wire's own `snake_case` field names, and results come back the
same way — no renaming, no wrapper objects to unlearn. The names are not guesswork: every body has a
`TypedDict` in `oblodai.contract.requests` and every response a `TypedDict` in
`oblodai.contract.models`, generated from the gateway, so editors autocomplete the fields and
`mypy` catches a typo before it reaches the API.

```python
from oblodai.contract.requests import PaymentBody

body: PaymentBody = {"amount": "25", "currency": "USDT"}
invoice = oblodai.payments.create(body)
```

### Async

```python
import asyncio
from oblodai.aio import AsyncOblodai


async def main() -> None:
    async with AsyncOblodai() as oblodai:
        invoice = await oblodai.payments.create({"amount": "25", "currency": "USDT"})
        async for payment in oblodai.payments.history(limit=50):
            print(payment["uuid"])


asyncio.run(main())
```

Both clients share one pure core: signing, envelope decoding, the retry decision and the idempotency
rules are I/O-free code that the sync and async transports both drive, so they cannot drift apart.

### Amounts

Amounts are decimal strings at the asset's own scale. Never `float()` them: a `float` in a request
body raises `ConfigError` (`sdk.float_amount`) before anything is sent. A `Decimal` is fine - it goes
out as its exact string, and the helpers take it too:

```python
from decimal import Decimal

from oblodai import add_amounts, amount_equals, compare_amounts

add_amounts("10.000000", "0.5")  # "10.500000"
compare_amounts("25", "25.0000")  # 0
amount_equals("25", "25.000000")  # True
add_amounts(Decimal("1.10"), "2.20")  # "3.30"
```

Never `<` or `sorted()` on the raw strings either — they compare lexicographically, and `"10" < "9"`
is `True`. Anything that is not a decimal string raises `AmountError` (also a `ValueError`).

## Sandbox / testing

A sandbox key drives a chainless copy of the gateway: fake balance from a faucet, simulated deposits
instead of blocks, and real signed webhooks. Integrate against it first — nothing here touches a
chain.

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

Repeat `sandbox.deposit` with the same `txid` to add confirmations. Rehearsal deliveries — from
`webhooks.test(kind, …)` and from the sandbox — are signed exactly like live ones and carry
`test: true` in the body (and `X-Webhook-Test: true`): check `delivery.is_test` (or
`webhooks.is_test_event(event)`) and never act on one as if money moved.
[`examples/sandbox.py`](examples/sandbox.py) walks the whole money path in about a second.

## Method overview

Sixteen namespaces cover all 107 routes of the gateway.

| Namespace | Methods | Routes |
| --------- | ------- | ------ |
| `payments` | `create` `info`/`get` `cancel` `history`/`list` `batch` `qr` `services` `send_email` `resend` `public_view` `select` `public_qr` | `/v1/payment*` `/v1/pay/{id}*` |
| `refunds` | `create` `resolve` `batch` | `/v1/payment/refund` `/v1/payment/resolve` `/v1/refund/batch` |
| `payouts` | `create` `validate` `calculate` `info`/`get` `cancel` `approve` `history`/`list` `mass` `batch` `services` `get_fee_config` `set_fee_config` `get_refund_fee_config` `set_refund_fee_config` | `/v1/payout*` |
| `payout_links` | `create` `info`/`get` `list` `cancel` `batch` `cheque` `claim_preview` `claim` | `/v1/payout/link*` `/v1/claim/{token}` |
| `payment_links` | `create` `info`/`get` `list` `toggle` `public_view` `checkout` | `/v1/payment/link*` `/v1/link/{id}*` |
| `batches` | `info` | `/v1/batch/info` |
| `transfers` | `to_personal` `to_user` `batch` | `/v1/transfer/*` |
| `wallets` | `create` `qr` `block` `refund_blocked_deposit` | `/v1/wallet*` |
| `webhooks` | `register` `rotate_secret` `deliveries` `test` `test_legacy` | `/v1/webhooks*` `/v1/test-webhook/{kind}` `/v1/payment/testing-webhook` |
| `documents` | `create_job` `job_info` `job_file` `statement` `balance_certificate` `fee_schedule` `ledger` `split_report` `batch_report` `link_report` `wallet_statement` `referrals_report` `download` | `/v1/documents/*` |
| `splits` | `create_rule` `list_rules` `delete_rule` `get_config` `set_config` `get_opt_in` `set_opt_in` | `/v1/split/*` |
| `settings` | `set_discount` `list_discounts` `get_accuracy` `set_accuracy` `get_auto_refund` `set_auto_refund` `list_accepted` `set_accepted` `get_payment_fee_config` `set_payment_fee_config` `list_auto_withdraw` `set_auto_withdraw` `delete_auto_withdraw` `list_api_allowlist` `add_api_allowlist` `remove_api_allowlist` `enable_api_allowlist` | `/v1/payment/*` `/v1/auto-withdraw/*` `/v1/api-allowlist/*` |
| `account` | `balance` `referral` `vrcs` | `/v1/balance` `/v1/referral/info` `/v1/vrcs` |
| `catalog` | `currencies` `exchange_rates` | `/v1/currencies` `/v1/exchange-rate/list` |
| `sandbox` | `faucet` `deposit` `webhooks` `replay` `reset` | `/v1/sandbox/*` |
| `merchants` | `create` `create_sandbox` | `/v1/merchants` `/v1/merchants/{id}/sandbox` |

Every method takes the same trailing keyword arguments (the fields of `oblodai.RequestOptions`):
`idempotency_key`, `timeout` (seconds, per attempt), `max_retries`, `extra_headers` (extra headers
for this call alone) and `request_id` (sent as `X-Request-ID`; a uuid4 when omitted). List methods also take `limit=` / `offset=`. Anything else raises `TypeError` before a
request is sent.

The payer-facing routes — `payments.public_view/select/public_qr`,
`payment_links.public_view/checkout`, `payout_links.claim_preview/claim` — need no credentials at
all. Document methods return a `FileResult(content, content_type, filename)`.

### Lists

List methods return a lazy `Page`. It requests nothing until you consume it:

```python
page = oblodai.payments.history({"limit": 50}).first()  # one page
page.items, page.total, page.has_pages

for payment in oblodai.payments.history({"limit": 50}):  # every page, fetched on demand
    print(payment["uuid"])

recent = oblodai.payouts.history({"limit": 50}).all(max_items=200)
```

`page.items` and `page.paginate` are shortcuts for the first page. On the async client the same
object is awaited (`await client.payments.history()`) or walked with `async for`.

### Statuses

- Payment: `select → created → confirm_check → paid | paid_over | wrong_amount | expired | cancelled`.
  `is_payment_paid` covers paid/paid_over; `wrong_amount` needs `refunds.resolve({...})`.
- Payout: `pending → approved → awaiting_cosign → broadcasting → sent → confirmed | failed | cancelled`.

```python
from oblodai import is_payment_paid, is_payout_final
```

## Webhooks

Register the endpoint once — the secret is returned once, at registration:

```python
endpoint = oblodai.webhooks.register("https://shop.example/oblodai/webhook")
endpoint_secret = endpoint["secret"]  # store it; it is not shown again
```

Verify every delivery over the **raw request bytes**, never a re-serialised parse:

```python
from oblodai import webhooks

delivery = webhooks.verify_delivery(raw_body, request.headers, secret=endpoint_secret)
event = delivery.event  # {"type": "payment"|"payout"|"wallet", ...}
if webhooks.is_stale(event, last_sequence_you_processed):
    return  # a retry that arrived after a newer state
if webhooks.is_known_event(event) and event["type"] == "payment":
    ...  # narrowed to the payment shape
```

An event kind newer than this SDK is returned, not refused — `is_known_event` is `False` and
`event["type"]` holds the raw string. Acknowledge it either way; refusing it would make the gateway
retry a delivery that is perfectly valid.

`SignatureError` and `WebhookPayloadError` mean different things: the first is a delivery that is
not from the gateway (answer **401** — and 401 only ever for a signature failure), the second an
authentic one whose body this receiver cannot read (`webhook.bad_payload`; answer **400**, since no
retry will fix it). The signature is checked before the freshness window, so a forged delivery never
learns what time this endpoint thinks it is.

Deduplicate on `delivery.id` (`X-Webhook-Id`, stable across retries). Rehearsal deliveries carry
`delivery.is_test`. During a secret rotation (`webhooks.rotate_secret`) pass `previous_secret=` for
at least 26 h — deliveries queued before the rotation stay signed with the old secret for their
whole retry life. `tolerance_sec` (default 300) bounds how stale a delivery may be.

A complete receiver is in [`examples/webhook_receiver.py`](examples/webhook_receiver.py).

## Errors

Everything raises a subclass of `OblodaiError`:

```python
from oblodai import OblodaiError, RateLimitError

try:
    oblodai.payouts.create({...})
except RateLimitError as err:
    ...  # err.retry_after
except OblodaiError as err:
    print(err.code, err.http_status, err.retryable, err.request_id, err.field)
```

`str(err)` is ready for a log line: `[payment.bad_amount] amount must be positive (request_id=rq-9)`
(the suffix only when there is an id); `err.message` stays the bare text.

| class | HTTP | when |
| ----- | ---- | ---- |
| `ValidationError` | 400 | malformed request or a broken business rule (`field` says which) |
| `AuthenticationError` | 401 | bad signature, unknown key, clock skew, IP not allowed |
| `PermissionDeniedError` | 403 | a valid key that may not do this (a disabled feature, an IP outside the allow-list) |
| `NotFoundError` | 404 | no such object |
| `ConflictError` / `IdempotencyConflictError` | 409 | state conflict; the same key with a different body |
| `RateLimitError` | 429 | too many requests (`retry_after`) |
| `UnavailableError` / `InternalError` | 503 / other 5xx | the gateway could not answer |
| `TransportError` | — | no response at all (`transport.timeout`, `transport.network`, `transport.deadline`) |
| `ConfigError` | — | raised before anything is sent (`sdk.bad_config`, `sdk.bad_header`, `sdk.bad_idempotency_key`, `sdk.idempotency_unsupported`, `sdk.missing_credentials`) |
| `SignatureError` | — | webhook verification failed — the delivery is not from the gateway |
| `WebhookPayloadError` | — | an authentic delivery whose body cannot be used (`webhook.bad_payload`) |
| `ResponseTooLargeError` | — | the response passed the size cap (`sdk.response_too_large`) |
| `AmountError` | — | a string handed to the money helpers is not a decimal amount (`sdk.bad_amount`) |

`err.retryable` is the gateway's own classification — the SDK has already retried what it should.
`err.retry_after` is its `Retry-After` in seconds (clamped to 24 h), `err.request_id` is what
support asks for, `err.synthetic` marks an answer that came from a proxy rather than the API, and
`err.to_dict()` is log-friendly and never contains the raw body.

Branch on `err.code`, which is always `family.reason`. Codes worth handling by name:
`payout.insufficient_funds` (retryable), `payout.funds_maturing` (retryable),
`idempotency.key_reused`, `invoice.not_payable`, `payment.not_found`,
`merchant.bad_signature`, `request.rate_limited`. The full catalogue is `oblodai.ERROR_CODES`
(469 codes) — the gateway's own list, so a code can be matched exactly instead of by substring.

## Retries, idempotency and timeouts

Whether a call may be repeated is not guessed from the shape of its path: it is
`ROUTES[key].safe`, the gateway's own read-only classification, carried in the contract snapshot.
A write the gateway does not deduplicate is never re-sent once it may have reached the gateway —
a transport error after the request left the socket could mean the payout already happened.

A create-type route gets a generated `Idempotency-Key`, reused across that call's retries, so a lost
response can never become a double payout. Pass your own (≤ 255 characters) to survive a process
restart:

```python
oblodai.payouts.create({...}, idempotency_key=f"payout-{order_id}")
```

Passing one to a route the gateway does not deduplicate raises `sdk.idempotency_unsupported` rather
than pretending the re-send is safe — list methods included, where it is refused rather than
dropped. Retries stop on the first non-retryable answer; `Retry-After` always wins over the
exponential backoff with jitter. Tune with `RetryOptions(max_retries=…, base_delay_ms=…)` (defaults:
2 retries, 250 ms base, 4 s cap, 30 s cap on an honoured `Retry-After`), or switch retries off with
`RetryOptions(max_retries=0)`.

Bounds: `timeout` (seconds, one attempt, default 30 s; per call too) and the client's `deadline`
(seconds, the whole call, retries included, default 90 s); `extra_headers` adds headers for this
call alone. Every request carries an `X-Request-ID` - yours (`request_id=`) or a generated uuid4,
the same for every attempt of the call. There is no `AbortSignal`
equivalent: cancel an async call by cancelling its task (`CancelledError` propagates untouched).

Signed requests carry a timestamp, so a machine with a wrong clock would fail authentication; the
client learns the offset from the gateway's own `Date` header and corrects for it (offsets beyond
24 h are treated as implausible and ignored). Redirects are never followed — a signature is only
valid for the URI it was signed for, and an injected HTTP client that follows one is caught and
turned into an error. Response bodies are read under a cap: 8 MiB for JSON, 64 MiB for documents,
beyond which the call raises `ResponseTooLargeError`.

## Configuration

Every option is a keyword argument to `Oblodai(...)` / `AsyncOblodai(...)`; an explicit argument
always wins over the environment.

| option | default | what it does |
| ------ | ------- | ------------ |
| `public_id`, `secret` | environment | the merchant's API key |
| `base_url` | `https://api.oblodai.com` | API origin; a path prefix (`https://gw.corp/oblodai`) is kept |
| `allow_insecure_base_url` | `False` | permits a non-loopback `http://` base URL |
| `admin_token` | environment | `X-Admin-Token` for `merchants.*` on a self-hosted gateway |
| `timeout` | `30.0` | seconds per attempt; an `httpx.Timeout` is accepted (its largest bound) |
| `deadline` | `90.0` | seconds for the whole call, retries included |
| `retry` | `RetryOptions()` | `max_retries`, `base_delay_ms`, `max_delay_ms`, `max_retry_after_ms` |
| `headers` | — | extra headers on every request |
| `logger` | none | anything with `debug/info/warning/error(message, fields)` |
| `http_client` | a private one | your own `httpx.Client` / `httpx.AsyncClient` |
| `env` | `os.environ` | the mapping the client reads its environment from |

With no arguments at all the client configures itself from the environment:

| variable | what it sets |
| -------- | ------------ |
| `OBLODAI_PUBLIC_ID` / `OBLODAI_SECRET` | the merchant's API key |
| `OBLODAI_ADMIN_TOKEN` | gates `merchants.*` on a self-hosted gateway |
| `OBLODAI_BASE_URL` | the API origin (default `https://api.oblodai.com`; a path prefix is kept) |
| `OBLODAI_LOG` | `debug` \| `info` \| `warning` \| `error` — structured logging to stderr |
| `OBLODAI_ALLOW_INSECURE` | `1` permits a non-loopback `http://` base URL |

A full annotated file is in [`.env.example`](.env.example) — those six variables are the whole
environment the client reads. A half-configured key (a `public_id` without its `secret`, or the
other way round) is a `ConfigError` at construction, not a 401 later.

**Secrets never reach the log.** Field values that carry a key, a signature, a cheque passcode or a
claim URL are redacted before they are handed to the logger, so even `OBLODAI_LOG=debug` — which
logs every attempt, its route, status and timing to stderr — cannot leak one. A `logging.Logger`,
structlog or a test double all fit the four-method protocol the transport calls.

### Self-hosted or local gateway

```python
Oblodai(base_url="http://127.0.0.1:8095", allow_insecure_base_url=True)
```

Plain `http://` is accepted for loopback without the flag; anything else needs it, so a signature
never leaves the host in the clear by accident. Merchant provisioning (`merchants.*`) is unsigned
and carries `X-Admin-Token` when `admin_token` is set.

## The contract snapshot

`contract/` — in the repository and in the sdist, not in the installed wheel — holds the gateway's
own export: the route registry, request schemas, all enums and error codes, signing vectors, golden
response bodies for every route and real signed webhook deliveries. It pins one core commit
(`CONTRACT_CORE_COMMIT`), and the 107 routes and 469 error codes this SDK exposes are exactly the
ones in it.

```python
from oblodai import CONTRACT_CORE_COMMIT, ROUTES

ROUTES["POST /v1/payout"].auth  # "key" - signed with the merchant's API key
ROUTES["POST /v1/payout"].idempotent  # True
ROUTES["POST /v1/payout"].safe  # False - never re-sent after a transport failure without a key
```

`scripts/codegen.py` turns the snapshot into `oblodai/contract/{routes,enums,requests,version}.py`,
and `scripts/gen_async.py` mirrors the resource layer into `oblodai/aio/resources/`. Both outputs
are checked by `scripts/check_drift.py` — it regenerates into a temporary directory and compares, so
the committed code cannot drift from the contract, in CI or locally (`make drift`).

To refresh: drop the newer export into `contract/`, run `make codegen`, then `make ci`. The contract
tests fail loudly on anything the snapshot changed — a new route, a renamed field, a moved error
code — which is the point.

## Development

```bash
git clone https://github.com/oblodai/oblodai-python && cd oblodai-python
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
make ci            # drift + ruff + mypy + unit and contract tests + packaging
make live          # the same, plus the live tier (needs OBLODAI_LIVE_URL)
make codegen       # regenerate the contract mirror and the async resources
```

Three test tiers: `tests/unit` (signing and webhook vectors, retry/idempotency/skew/URL rules over a
scripted HTTP layer), `tests/contract` (every route is wired to the right method, path, auth and
idempotency header; every golden body matches its model key-for-key; the documentation is checked
like code) and `tests/live` (a real gateway: onboard, invoice, deposit, payout, refund, links,
documents).

See also [AGENTS.md](AGENTS.md) for the agent-facing summary, [CHANGELOG.md](CHANGELOG.md) for
what changed, [MIGRATION-1.3.md](MIGRATION-1.3.md) for the move from 1.2 and
[RELEASING.md](RELEASING.md) for how a version reaches PyPI.

## License

MIT — see [LICENSE](LICENSE).
