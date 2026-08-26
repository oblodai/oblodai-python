# Oblodai Python SDK

Official Python client for the [Oblodai](https://oblodai.com) crypto payment gateway: invoices,
payouts, refunds, payout links, static wallets, webhooks, documents — the whole merchant API,
typed end to end and verified against the gateway's own contract snapshot.

- Python ≥ 3.9, one runtime dependency (`httpx`), synchronous **and** asynchronous clients.
- Every route the gateway exposes (107) has a method here; request and response types are generated
  from the gateway's contract.
- Retries driven by the API's own `retryable` flag, automatic idempotency keys, clock-skew correction.
- `oblodai.webhooks`: signature verification that needs no client and no API key.
- Writing code with an AI agent? Point it at [AGENTS.md](AGENTS.md).

```bash
pip install oblodai
```

## Start in the sandbox

Get your keys in the Oblodai dashboard. A **sandbox key** (`test_…`) drives a chainless copy of the
gateway — fake balance from a faucet, simulated deposits, real webhooks — so integrate against it first.

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

With no arguments the client reads `OBLODAI_PUBLIC_ID`, `OBLODAI_SECRET`, `OBLODAI_BASE_URL`,
`OBLODAI_PAYOUT_PUBLIC_ID`, `OBLODAI_PAYOUT_SECRET` and `OBLODAI_ADMIN_TOKEN` from the environment.

Prices in fiat: `{"amount": "25", "currency": "USD", "to_currency": "USDT"}` — `currency` is what
you charge, `to_currency` the asset the payer sends. Runnable scripts live in [`examples/`](examples).

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

### Two keys

The gateway issues a **payment key** (`pk_…`) and a **payout key** (`wk_…`). Sandbox keys are both at
once; live keys are separate, and money-out routes need the payout one: `payouts.*`, `refunds.*`,
`payout_links.*`, `transfers.*`, `splits.*`, `wallets.refund_blocked_deposit`, auto-withdraw, the IP
allow-list, `webhooks.rotate_secret`, `sandbox.faucet`/`reset`. Pass both pairs and the SDK picks the
right one per call:

```python
Oblodai(public_id=..., secret=..., payout_public_id=..., payout_secret=...)
```

A call with the wrong kind is a 403 `merchant.wrong_key_kind`.

## Resources

| Namespace        | Methods |
| ---------------- | ------- |
| `payments`       | `create` `info`/`get` `cancel` `history`/`list` `batch` `qr` `services` `send_email` `resend` `public_view` `select` `public_qr` |
| `refunds`        | `create` `resolve` `batch` |
| `payouts`        | `create` `validate` `calculate` `info`/`get` `cancel` `approve` `history`/`list` `mass` `batch` `services` `get_fee_config` `set_fee_config` `get_refund_fee_config` `set_refund_fee_config` |
| `payout_links`   | `create` `info`/`get` `list` `cancel` `batch` `cheque` `claim_preview` `claim` |
| `payment_links`  | `create` `info`/`get` `list` `toggle` `public_view` `checkout` |
| `batches`        | `info` |
| `transfers`      | `to_personal` `to_user` `batch` |
| `wallets`        | `create` `qr` `block` `refund_blocked_deposit` |
| `webhooks`       | `register` `rotate_secret` `deliveries` `test` `test_legacy` |
| `documents`      | `create_job` `job_info` `job_file` `statement` `balance_certificate` `fee_schedule` `ledger` `split_report` `batch_report` `link_report` `wallet_statement` `referrals_report` `download` |
| `splits`         | `create_rule` `list_rules` `delete_rule` `get_config` `set_config` `get_opt_in` `set_opt_in` |
| `settings`       | `set_discount` `list_discounts` `get_accuracy` `set_accuracy` `get_auto_refund` `set_auto_refund` `list_accepted` `set_accepted` `get_payment_fee_config` `set_payment_fee_config` `list_auto_withdraw` `set_auto_withdraw` `delete_auto_withdraw` `list_api_allowlist` `add_api_allowlist` `remove_api_allowlist` `enable_api_allowlist` |
| `account`        | `balance` `referral` `vrcs` |
| `catalog`        | `currencies` `exchange_rates` |
| `sandbox`        | `faucet` `deposit` `webhooks` `replay` `reset` |
| `merchants`      | `create` `create_sandbox` |

Every method takes the same trailing keyword arguments: `idempotency_key`, `timeout_ms`,
`deadline_ms`, `prefer_payout_key`.

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

### Errors

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

| class | when |
| ----- | ---- |
| `ValidationError` | 400 — malformed request or a broken business rule (`field` says which) |
| `AuthenticationError` | 401 — bad signature, unknown key, clock skew, IP not allowed |
| `PermissionError` | 403 — valid key, wrong kind or a disabled feature |
| `NotFoundError` | 404 |
| `ConflictError` / `IdempotencyConflictError` | 409 — state conflict; the same key with a different body |
| `RateLimitError` | 429 |
| `UnavailableError` / `InternalError` | 503 / other 5xx |
| `TransportError` | no response at all (`transport.timeout`, `transport.network`, `transport.deadline`) |
| `ConfigError` | raised before anything is sent |
| `SignatureError` | webhook verification failed |

`err.retryable` is the gateway's own classification — the SDK has already retried what it should.
`err.synthetic` marks an answer that came from a proxy rather than the API. `err.to_dict()` is
log-friendly and never contains the raw body. Codes worth handling by name:
`payout.insufficient_funds` (retryable), `payout.funds_maturing` (retryable),
`idempotency.key_reused`, `invoice.not_payable`, `payment.not_found`, `merchant.wrong_key_kind`,
`request.rate_limited`. The full list is `oblodai.ERROR_CODES` (468 codes).

### Retries and idempotency

A create-type route gets a generated `Idempotency-Key`, reused across that call's retries, so a lost
response can never become a double payout. Pass your own to survive a process restart:

```python
oblodai.payouts.create({...}, idempotency_key=f"payout-{order_id}")
```

Passing one to a route the gateway does not deduplicate raises `sdk.idempotency_unsupported` rather
than pretending the re-send is safe. Transport failures and envelope-less proxy answers are retried
only on read-only routes and on keyed writes; `Retry-After` always wins over the backoff. Tune with
`RetryOptions(max_retries=…, base_delay_ms=…)`, or switch retries off with `RetryOptions(max_retries=0)`.

There is no `AbortSignal` equivalent: cancel an async call by cancelling its task (`CancelledError`
propagates untouched), and bound any call with `timeout_ms` (per attempt) and `deadline_ms`
(the whole call, retries included).

### Webhooks

```python
from oblodai import webhooks

delivery = webhooks.verify_delivery(raw_body, request.headers, secret=endpoint_secret)
event = delivery.event  # {"type": "payment"|"payout"|"wallet", ...}
if webhooks.is_stale(event, last_sequence_you_processed):
    return  # a retry that arrived after a newer state
```

Rehearsal deliveries (`webhooks.test`, sandbox) are signed exactly like live ones and carry
`test: true` in the body (and `X-Webhook-Test: true`) — check `delivery.is_test` (or
`webhooks.is_test_event(event)`) and never act on one as if money moved.

Verify over the **raw request bytes**, never a re-serialized parse. Deduplicate on `delivery.id`
(`X-Webhook-Id`, stable across retries). During a secret rotation pass `previous_secret=` for at
least 26 h — deliveries queued before the rotation stay signed with the old secret for their whole
retry life. `tolerance_sec` (default 300) bounds how stale a delivery may be.

A complete receiver is in [`examples/webhook_receiver.py`](examples/webhook_receiver.py).

### Money

Amounts are decimal strings at the asset's own scale. Never `float()` them:

```python
from oblodai import add_amounts, compare_amounts, amount_equals

add_amounts("10.000000", "0.5")  # "10.500000"
compare_amounts("25", "25.0000")  # 0
```

### Self-hosted or local gateway

```python
Oblodai(base_url="http://127.0.0.1:8095", allow_insecure_base_url=True)
```

Plain `http://` is accepted for loopback without the flag; anything else needs it, so a signature
never leaves the host in the clear by accident. A base URL may carry a path prefix
(`https://gw.corp/oblodai`) and it is kept. Merchant provisioning (`merchants.*`) is unsigned and
carries `X-Admin-Token` when `admin_token` is set.

## The contract snapshot

`contract/` ships the gateway's own export: the route registry, request schemas, all enums and error
codes, signing vectors, golden response bodies for every route and real signed webhook deliveries.
`scripts/codegen.py` turns it into `oblodai/contract/{routes,enums,requests,version}.py`, and
`scripts/gen_async.py` mirrors the resource layer into `oblodai/aio/resources/`. Both are checked in
CI by `scripts/check_drift.py`, so the committed code cannot drift from the contract.

```python
from oblodai import ROUTES, CONTRACT_CORE_COMMIT

ROUTES["POST /v1/payout"].auth  # "payout"
ROUTES["POST /v1/payout"].idempotent  # True
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
make ci            # drift + ruff + mypy + unit and contract tests
make live          # the same, plus the live tier (needs OBLODAI_LIVE_URL)
make codegen       # regenerate the contract mirror and the async resources
```

Three test tiers: `tests/unit` (signing and webhook vectors, retry/idempotency/skew/URL rules over a
scripted HTTP layer), `tests/contract` (every route is wired to the right method, path, auth and
idempotency header; every golden body matches its model key-for-key) and `tests/live` (a real
gateway: onboard, invoice, deposit, payout, refund, links, documents).

## Licence

MIT.
