# Oblodai Python SDK

> [Читать по-русски →](README.ru.md)

The official Python SDK for the **Oblodai** payment gateway: accepting payments, payouts, mass
operations (batches), payment and payout links, splits, e-mail invoices, static wallets,
webhooks, developer sandbox. Sync and async clients, request signing, response parsing into pydantic models,
typed errors, and automatic retries.

> **v1.1.0 — breaking change to idempotency.** The SDK **no longer fills in** `order_id`.
> Protection against duplicates on retries comes from the `Idempotency-Key` header, which the SDK
> generates itself (once per call). See the "Retries and idempotency" section for details.

> **Base URL — `https://` only.** The default is `https://api.oblodai.com`; override
> `base_url` at initialization if needed. The `http://` scheme is **rejected**
> (`ValueError` when creating the client): over it the `X-Signature` signing header travels in
> plain text and can be intercepted by any middleman. **The exception is local setups on a loopback
> host:** `localhost`, `127.0.0.1`, `::1` (e.g. `http://localhost:8095`) work over `http`,
> because that traffic never leaves the machine.

## Installation

```bash
pip install oblodai
```

Requires Python 3.9+. Dependencies: `httpx`, `pydantic>=2`.

## Where to get keys

Keys are issued in the **Oblodai dashboard** — [oblodai.com](https://oblodai.com), API keys
section. A pair consists of:

* **public id** — the key identifier, sent in the `X-Public-Id` header;
* **secret** — used to sign every request (`X-Signature`). The secret **is shown once,
  when the key is created**, and never appears in the dashboard again. Lost it — issue a new one.

For development, take a **test (sandbox) key**: a public id like `test_…`, a secret like
`oblodai_test_…`. It hits the same endpoints but moves no money — see the
["Sandbox / testing"](#sandbox--testing-v120) section right after the quick start;
it is the best way to begin an integration. A live key differs only in its values — the code is the same.

## Credentials

Keep keys in environment variables (see `.env.example`) rather than in code:

```bash
export OBLODAI_PUBLIC_ID=test_...           # live keys have no test_ prefix
export OBLODAI_SECRET=oblodai_test_...      # live: oblodai_live_...
# optional:
export OBLODAI_BASE_URL=https://api.oblodai.com
```

```python
from oblodai import OblodaiClient

client = OblodaiClient.from_env()   # reads OBLODAI_PUBLIC_ID / OBLODAI_SECRET / OBLODAI_BASE_URL
```

## Quick start (sync)

```python
from oblodai import OblodaiClient

# or explicitly (equivalent to from_env above):
client = OblodaiClient(
    public_id="test_...",
    secret="oblodai_test_...",
    base_url="https://api.oblodai.com",  # set your real one
)

payment = client.payments.create(
    amount="10",
    currency="USD",
    order_id="order-1",
    to_currency="USDT",
    network="tron",
)

print(payment.address)  # address to pay to
print(payment.url)      # hosted payment page
```

A **test** key (`test_…` / `oblodai_test_…`) is used here. The same code works with a live
key — only the key changes.

> **About `payment.url` (and `claim_url` on payout links).** These links are built by the gateway
> from its public base URL. In production it is mandatory (the gateway won't start without it), but on a **local
> setup** without `GATEWAY_PUBLIC_BASE_URL` both fields come back as an **empty string**. This is not an SDK bug
> and not a gateway bug. If you run locally — build the link yourself from `payment.uuid`
> (or `claim_token` for a payout link), or host your own payment page on the public
> endpoints (see "Custom checkout").

## Sandbox / testing (v1.2.0)

The gateway has a developer sandbox with **test keys**: a public id with the `test_` prefix,
a secret with the `oblodai_test_` prefix. **Business endpoints do not change** and work exactly
the same with a test key — the integration code is identical for test and production; ONLY the
key changes between them:

```bash
# test
export OBLODAI_PUBLIC_ID=test_...
export OBLODAI_SECRET=oblodai_test_...
# production — same code, different key
export OBLODAI_PUBLIC_ID=oblodai_...
export OBLODAI_SECRET=oblodai_live_...
```

The `is_test_key(public_id)` helper returns `True` for a test key (`test_` prefix).

New — the `client.sandbox` group: five test-only endpoints that stand in for buyer actions
("the buyer paid on-chain" and the like). **For test code only** — these endpoints do not exist
in production, and a live key gets HTTP 403 `sandbox.live_key`. Do not call
`client.sandbox.*` from production code.

```python
from oblodai import OblodaiClient

client = OblodaiClient(public_id="test_...", secret="oblodai_test_...")

# 1. Regular business code: create an invoice
payment = client.payments.create(amount="10", currency="USD", order_id="t-1",
                                 to_currency="USDT", network="tron")

# 2. "Pay on-chain" on the buyer's behalf
client.sandbox.simulate_deposit(invoice_id=payment.uuid)   # exactly the amount due, confirmed immediately

# 3. Regular business code: verify the invoice is paid
assert client.payments.info(uuid=payment.uuid).payment_status == "paid"

# 4. Test balance faucet (≤ 1000000 per call) — then run a payout
client.sandbox.faucet(asset="USDT", amount="1000")
client.payouts.create(amount="25", currency="USDT", network="tron",
                      address="T...", order_id="w-1")
```

The rest of the group's methods:

```python
# underpayment / overpayment / an "in-flight" deposit
# amount is given in the invoice's payment currency (pay_amount); less than the amount due — underpayment,
# more — overpayment (paid_over). Omitted — exactly the amount due is paid.
client.sandbox.simulate_deposit(invoice_id=..., amount="5")   # partial payment
# → payment_status becomes "wrong_amount_waiting", NOT "wrong_amount": the invoice is still alive and waits
#   for the remainder. resolve here responds 409 resolution.not_underpaid. The invoice moves to "wrong_amount"
#   only after lifetime expires (minimum 300 s) — create the invoice with a short lifetime
#   if you want to see this transition in a test.
client.sandbox.simulate_deposit(invoice_id=..., confirmations=1,      # arrives unconfirmed
                                txid="tx-1")
client.sandbox.simulate_deposit(invoice_id=..., confirmations=20,     # repeat with the SAME txid
                                txid="tx-1")                          # deepens confirmations

client.sandbox.reset()               # see below: NOT a "clean slate"

# webhook inspector: list → take .id → replay(delivery_id=<that .id>)
deliveries = client.sandbox.list_webhooks()   # up to 50, newest first, with a payload field
d = deliveries[0]
print(d.id, d.event_type, d.status, d.payload)
res = client.sandbox.replay_webhook(d.id)     # EXACTLY d.id — that is the delivery_id
assert res.delivery_id == d.id and res.requeued
```

About names in this pair: in the `list_webhooks()` output the delivery identifier lives in the
**`.id`** field (`SandboxDelivery.id`), while `replay_webhook` takes it positionally as
**`delivery_id`** (that's the field's name in the body of `POST /v1/sandbox/webhooks/replay`, and it
is also returned in the `SandboxReplayResult.delivery_id` response). They are the same value — the
delivery uuid; the different names at the two ends are just different roles of one identifier.

Caveats:

- **`sandbox.reset()` is not a "clean slate".** It cancels invoices **only** in the
  `created` and `select` statuses and zeroes balances (with a compensating entry — the journal is append-only,
  so the history of your experiments stays readable). An invoice that already **has a visible deposit**
  (`confirm_check`, `wrong_amount_waiting`) is **deliberately left alone** by reset: cancelling it would let
  the deposit confirm into a cancelled invoice and credit money without an event. This is a gateway decision,
  not an unfinished feature. The response carries `invoices_cancelled` and `balances_zeroed`: if a test
  sees a "leftover" invoice after reset, check against these numbers rather than assuming reset is broken. If a test
  needs full isolation — create a new invoice with a new `order_id` instead of relying on reset.
- **"Shallow" deposits do NOT mature on their own.** A deposit with fewer `confirmations` than required
  leaves the invoice in `confirm_check` **forever**: the sandbox will not re-emit the transaction and
  will not top anything up in the background. The only way to drive the invoice to `paid` is to repeat
  `simulate_deposit` with the **same `txid`** and a larger `confirmations`.
- **The ~10 minutes are about something else.** That is the maturity **hold on payouts**: freshly arrived funds
  cannot be withdrawn for a while, and `payouts.create` fails with
  `payout.funds_maturing` until the hold expires. The hold is lifted by a background job based on the age of the funds
  (10 minutes by default in the sandbox, configurable on the gateway side). This timer has nothing to do with
  the invoice's confirmation depth.
- **UTXO networks (Bitcoin and the like)** behave as in production: there is no auto-refund of overpayment
  and the payer's address is unknown — a refund requires an explicit `address`
  (see `payments.refund` / `payments.resolve`).
- `sandbox.list_webhooks` is the only **signed GET** in the SDK: the signature is computed over
  the same canonical string with an empty body (`{ts}\nGET\n/v1/sandbox/webhooks\n`).


## Async

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

The sync client supports the context manager too (`with OblodaiClient(...) as client:`).

## Statuses

### Payment (`payment.payment_status`)

| Status | Meaning | Terminal |
| --- | --- | --- |
| `check` | invoice created, no payment seen yet | no |
| `select` | currency-agnostic invoice: the buyer has not picked a currency/network yet (see `payments.public_select`) | no |
| `confirm_check` | payment seen, waiting for network confirmations | no |
| `wrong_amount_waiting` | a **partial** payment was seen, waiting for the remainder — the invoice is still alive | no |
| `wrong_amount` | the invoice **closed** underpaid | yes |
| `paid` | paid in full (within the `accuracy_payment_percent` tolerance) | yes |
| `paid_over` | overpaid; the excess goes to auto-refund if it is enabled and the network supports it | yes |
| `cancel` | expired or cancelled | yes |

The response carries a boolean `is_final` field — use it rather than your own list of statuses.

**`wrong_amount_waiting` and `wrong_amount` are different things, and confusing them is costly.** While the
invoice has not expired, a partial payment keeps it in `wrong_amount_waiting`: the buyer can still pay the rest,
and then the invoice becomes `paid`. It moves to `wrong_amount` only after its lifetime expires
(`lifetime`, minimum 300 s). `payments.resolve` works **only** with `wrong_amount`; on
`wrong_amount_waiting` the gateway responds `409 resolution.not_underpaid`.

### Payout (`payout.status`)

| Status | Meaning |
| --- | --- |
| `check` | created, awaiting approval (`payouts.approve`) |
| `process` | approved: on its way to or already in the network |
| `paid` | confirmed by the network |
| `fail` | failed |
| `cancel` | cancelled |

## Verifying webhooks

The webhook signature differs from the request signature — the SDK handles both. For incoming webhooks,
take the **raw body** and the `X-Webhook-Timestamp` / `X-Webhook-Signature` headers.

> **The webhook secret is NOT the API key secret.** The signature must be verified with the secret
> returned by `client.webhooks.register(url)` (the `.secret` field) — a separate **endpoint** secret.
> If you plug `OBLODAI_SECRET` (the API key secret) in here, verification will fail on **every**
> webhook. Save `register().secret` at registration time: it is not issued again.

> **`register()` is an upsert of the project's SINGLE endpoint, not "add another one".**
> Calling it again with a DIFFERENT URL does not create a second endpoint: it returns the **same**
> `endpoint_id`, deliveries move to the new URL, and the old one silently goes quiet. The secret
> is intentionally **preserved**: deliveries already queued are signed with it, and changing the secret
> would orphan them (401 → retries → dead-letter → lost `paid`/payout events). The practical
> consequence: to serve multiple recipients, split them by **project**
> (one key per project), not by repeated `register()` calls.

```python
from flask import Flask, request
from oblodai import construct_event, OblodaiSignatureError

app = Flask(__name__)
WEBHOOK_SECRET = "b7c1e9..."  # from client.webhooks.register()

@app.post("/oblodai/callback")
def callback():
    raw = request.get_data()  # the RAW body — do not re-serialize

    # Test bodies (is_test) are unsigned
    import json
    if json.loads(raw).get("is_test"):
        return "ok", 200

    try:
        event = construct_event(
            WEBHOOK_SECRET,
            raw,
            request.headers,          # verifies the signature AND freshness (replay protection)
        )
    except OblodaiSignatureError:
        return "bad signature", 403

    if event["type"] == "payment" and event["status"] == "paid":
        # mark order event["order_id"] as paid (idempotent by uuid + status)
        pass
    return "ok", 200
```

`construct_event` and `verify_webhook` check freshness within a 5-minute window by default
(`max_age_seconds=300`). Pass `max_age_seconds=0` to disable.

## Error handling

All API errors are instances of `OblodaiAPIError` with a machine-readable `.code`. Branch on the code.

```python
from oblodai import OblodaiAPIError

try:
    client.payouts.create(
        amount="25", currency="USDT", network="tron",
        address="T...", order_id="payout-1",
    )
except OblodaiAPIError as e:
    if e.code == "payout.insufficient_funds":
        ...  # not enough funds
    elif e.code == "payout.funds_maturing":
        ...  # funds are still maturing: e.is_retriable == False — do not retry yourself,
             # wait for the hold to lift and call again later (see "Retries and idempotency")
    print(e.code, e.status, e.message)
```

### Field name validation

Create methods accept fields as `**kwargs` and send them in the body of the signed request.
Previously a typo in a name **raised no error**: the gateway (like any JSON parser) ignores unknown
keys — and a money operation quietly executed with a different meaning. `amout="1"` instead of
`amount="1"` created an invoice for the wrong amount, `expires_in_hour` instead of `expires_in_hours` gave
a payout link a 1-hour lifetime, `percnt` instead of `percent` zeroed the partner's share. In every
case the response looked successful.

Now names are checked against an allowlist of the fields the gateway itself supports, **before** signing and
sending; an unknown name is a `TypeError` with a hint:

```python
client.payments.create(amont="10", currency="USD", order_id="o-1")
# TypeError: payments.create(): unknown field: 'amont'. Did you mean: 'amount'?
#            Allowed fields: accuracy_payment_percent, additional_data, amount, currency, ...
```

**All** money-moving create methods are checked: `payments.create`, `payouts.create`,
`payout_links.create`, `payment_links.create`, `splits.create_rule` — identically in the sync and async
clients. (In async methods the check lives in the coroutine body, so the `TypeError`
arrives on `await`, not at call time; the request still never leaves.)
The field lists are in `oblodai._params` (`PAYMENT_FIELDS`, `PAYOUT_FIELDS`, `PAYOUT_LINK_FIELDS`,
`PAYMENT_LINK_FIELDS`, `SPLIT_RULE_FIELDS`). Known fields work exactly as before: the list
describes what the gateway accepts anyway — these are not new restrictions, just a refusal to stay silent about a typo.
The error is a `TypeError`, not an `OblodaiAPIError`: it never reaches the API, no request is sent.

### Error classes

| Class | When |
|---|---|
| `OblodaiAPIError` | The API returned an `error` envelope. Has `.code`, `.status`, `.is_retriable`. |
| `OblodaiConnectionError` | The network is unreachable. |
| `OblodaiTimeoutError` | The request timed out. |
| `OblodaiSignatureError` | Webhook signature verification failed. |
| `OblodaiError` | Base class for all of the above. |

## Retries and idempotency

Transient errors (`5xx`, `429`, network failures) are retried automatically with
exponential backoff and jitter (`Retry-After` is honored on `429`). Request errors
(`4xx`) are not retried. `payout.funds_maturing` is a terminal error (the funds are still maturing)
and is NOT retried automatically.

```python
from oblodai import OblodaiClient, RetryConfig

client = OblodaiClient(
    public_id="...", secret="...",
    retry=RetryConfig(max_attempts=4, initial_delay=0.5, max_delay=30.0),
    # retry=None — disable
)
```

**How duplicate protection works (v1.1.0).** On creating calls (`payments.create`,
`payments.refund`, `payments.resolve`, `payouts.create`, `payouts.create_mass`, all
`create_batch`, `account.transfer_to_personal`, `payout_links.create`,
`payout_links.create_batch`, `wallets.blocked_address_refund`) the SDK generates an `Idempotency-Key`
header (uuid4) **once, before the retry loop** — all internal retries go out with the very same key,
so a timeout or a dropped connection cannot create a duplicate invoice or transfer. The header is not
part of the request signature.

```python
# your own idempotency key — goes into the HEADER, never into the request body
client.payments.create(amount="10", currency="USD", order_id="ord-1",
                       idempotency_key="my-op-42")
```

- **`order_id` is sent as is** — the SDK no longer fills it in or rewrites it
  (in v1.0.x an empty `order_id` was replaced with `idem-<uuid>`). It is your business identifier:
  set it explicitly and persist it BEFORE the call, so you can find the payment later via `payments.info`.
- **Payouts:** `order_id` is always required (an API requirement).
- **Payout links (`payout_links.create` / `create_batch`)** reserve money, so as of
  v1.2.0 they also go out with an `Idempotency-Key`, and the gateway **honors** it: a repeat with the
  same key replays the first response (same link, same `claim_token`, `Idempotent-Replayed:
  true` in the response), and the balance is debited **exactly once**. Without the header, two identical calls
  will create TWO links. The per-link `reference` remains the second, durable layer of protection — it
  works both without the header and when a batch response is too large for the cache (see below).
- **`wallets.blocked_address_refund`** is protected differently and more strongly: the gateway itself builds
  a deterministic reference `refund-wallet:<wallet_id>`, takes a per-wallet advisory lock, and
  inside the lock returns the already-created payout. A repeat — including a concurrent one, and even
  with no headers at all — returns the SAME payout; a second one is never created. One caveat: a repeat with a DIFFERENT
  `address` returns the first payout to the FIRST address (the address is not part of the reference).
- **`payouts.approve`** needs no header: it is a state transition; only
  `pending` is accepted, otherwise 409 `payout.not_pending`. Read that 409 as "already approved", not as
  a failure, and check the status via `payouts.info`.

### Idempotency response codes (payout links)

| Code | HTTP | When | Retried by the SDK |
|---|---|---|---|
| `idempotency.key_reused` | 400 | same key with a DIFFERENT request body | no |
| `idempotency.bad_key` | 400 | key longer than 255 characters | no |
| `idempotency.in_progress` | 409 | concurrent repeat while the first is still running | no |
| `idempotency.unavailable` | 503 | idempotency store unavailable (fail-closed by design) | **yes** |
| `payoutlink.duplicate_reference` | 409 | `reference` already taken (used to be a 500) | no |

The SDK's classification (`OblodaiAPIError.is_retriable`) matches this: `4xx` (including
both 409s and both 400s) are terminal, `5xx`/`429` are transient. The 500 → 409 change on a duplicate
`reference` matters for exactly this reason: the SDK used to spin useless retries; now the error is
returned to the caller immediately.

## New in v1.1.0

### Mass operations (batches)

Up to 5000 payments/refunds/payouts in one signed request (a single rate-limit mark).
Processing is in the background: submission returns a `batch_id`, results come via `batches.info`.

```python
sub = client.payments.create_batch([
    {"amount": "10", "currency": "USD", "order_id": "a-1"},
    {"amount": "20", "currency": "EUR", "order_id": "a-2"},
], on_error="continue")   # "continue" (default) or "stop"

info = client.batches.info(sub.batch_id, limit=100)
if info.done:                       # status == "completed"
    print(info.succeeded, info.failed)
    for item in info.items:
        print(item.idx, item.status, item.result or item.error)

client.payments.refund_batch([{"uuid": "p1", "reference": "r-1", "amount": "5"}])
client.payouts.create_batch([{"amount": "5", "currency": "USDT", "network": "tron",
                              "address": "T...", "order_id": "w-1"}])
```

Deduplication keys within a batch: payments/payouts require an `order_id` on every item,
refunds — a `reference` plus the invoice's `uuid`/`order_id`.

> **`client.refunds` is deprecated.** Batch refunds used to be offered as
> `client.refunds.create_batch(...)`. It is **the same thing** as `client.payments.refund_batch(...)`:
> one `POST /v1/refund/batch` endpoint, one body, one idempotency — just two names for
> one operation. Moreover, the `refunds` group exists **only in the Python SDK** (in TS, Go, Rust, and PHP
> batch refunds live on payments), so code using it does not port between languages.
> **Nothing has been removed:** `client.refunds.create_batch(...)` works as before, but accessing
> `client.refunds` emits a `DeprecationWarning`; removal is planned for 2.0. The canonical path is
> **`client.payments.refund_batch(...)`**.
>
> ```python
> # before
> client.refunds.create_batch([...])        # DeprecationWarning
> # after
> client.payments.refund_batch([...])       # canonical, same endpoint and same result
> ```
>
> Python hides `DeprecationWarning` outside `__main__` by default — to see it
> in your own code, run the interpreter with `-W default::DeprecationWarning` (in pytest they
> are visible out of the box).

### Payment links

A reusable link: many people pay through it, each payment gets its own invoice.

```python
link = client.payment_links.create(amount_mode="open", currency="USD", title="Donation")
print(link.url)

client.payment_links.list(limit=50)
client.payment_links.info(link.link_id)          # + payments made through the link
client.payment_links.toggle(link.link_id, active=False)

# public (unsigned) — what your payment page calls
client.payment_links.public_get(link.link_id)
client.payment_links.checkout(link.link_id, amount="10", currency="USD", network="tron")
```

**What this resource is called.** The canonical name is **`client.payment_links`**; that exact name is used
across all Oblodai SDKs (`paymentLinks` in JS and PHP, `payment_links` in Python and Rust, `PaymentLinks`
in Go), so code using it ports between languages without renames. **`client.links` is a
documented alias** for the same object: it is not going anywhere, but prefer
`payment_links` in new code.

```python
client.links is client.payment_links   # True — one and the same object
```

### Payout links ("crypto checks")

You reserve an amount without knowing the recipient's wallet; the recipient opens the `claim_url`
and enters an address themselves. Requires a PAYOUT/API key.

```python
link = client.payout_links.create(
    currency="USDT", network="tron", amount="25",
    reference="bonus-42",        # durable dedup across calls; internal retries are covered
                                 # by the Idempotency-Key header, which the gateway honors
    expires_in_hours=720,        # set EXPLICITLY: with 0/absent, the lifetime is clamped to 1 hour
    email="user@example.com",    # optional: an e-mail with a "Claim funds" button
)
print(link.claim_token)          # claim_token/claim_url are returned ONLY here — save them
print(link.claim_url)            # locally, without GATEWAY_PUBLIC_BASE_URL, this is an EMPTY string

client.payout_links.create_batch([{...}, ...])   # up to 500 links, a shared batch_id
client.payout_links.list(limit=50)
client.payout_links.info(link.link_id)           # after claim: payout_id, claim_address
client.payout_links.cancel(link.link_id)         # funded only → the reserve is returned

# public (unsigned) — for your own claim page
client.payout_links.claim_info(token)                    # GET /v1/claim/{token}
client.payout_links.claim(token, address="T...", memo=None)
```

**Link batches — put a `reference` on every item.** The gateway does not cache a response larger
than 256 KB, and then a repeat with the same `Idempotency-Key` executes AGAIN; a unique
`reference` is the layer that still stops the duplicate in that case (409
`payoutlink.duplicate_reference`). One more quirk: a partially failed batch replays
AS IS — failed items are not re-executed under the same key; resubmit them with a NEW key.

### Splits

A share of every incoming payment automatically goes to a partner.

```python
client.splits.split_to_address(address="T...", network="tron", percent=10, note="partner A")
client.splits.split_to_merchant(merchant_id="m2", percent=5)     # reversible on refunds
client.splits.list_rules()
client.splits.delete_rule(rule_id)
client.splits.get_config() / client.splits.set_config(refund_hold_hours=24)
```

### E-mail invoice and underpayment resolve

```python
client.payments.send_email(uuid=payment.uuid, email="buyer@example.com")

# resolve works ONLY for an invoice that CLOSED underpaid (payment_status ==
# "wrong_amount"). While the invoice is alive and waiting for the remainder (wrong_amount_waiting) — 409 resolution.not_underpaid.
info = client.payments.info(uuid=payment.uuid)
if info.payment_status == "wrong_amount":
    client.payments.resolve(uuid=payment.uuid, action="accept")   # keep the partial payment
    # or return it to the payer (address defaults to the recorded payer_address):
    # client.payments.resolve(uuid=payment.uuid, action="refund")
```

**An underpayment passes through two states, and resolve is available only in the second.** Until the
invoice's `lifetime` expires, a partial payment keeps it in `wrong_amount_waiting` — the buyer can still
pay the rest. `wrong_amount` arrives when the invoice has closed underpaid; that is when the
accept/refund choice appears. Calling `resolve` in the first state gets `409 resolution.not_underpaid`
(the gateway returns the actual status in the error message). See the "Statuses" section for details.

`action="accept"` additionally suppresses the auto-refund of the underpayment, and `action="refund"` requires
a PAYOUT/API key. Both are idempotent via the `Idempotency-Key` header (your own — the
`idempotency_key` kwarg); `refund` also has a per-refund `reference` key.

## Internal transfers (v1.2.0)

A fee-free transfer from the merchant balance to the personal wallet of a **platform user**
(the money never goes on-chain — it is an internal ledger entry). `to_user_id` is the platform
user's id (a UUID string), **NOT a username**: a username resolves to an id via the public
dashboard profile. Requires a PAYOUT/API key.

```python
res = client.account.transfer_to_user(
    to_user_id="5c3f6a1e-...",     # platform user's UUID
    amount="50", currency="USDT",
    order_id="salary-2026-07",     # optional — your business identifier
)
print(res.recipient_balance)       # the recipient's new balance

# a payroll batch (up to 5000 transfers) — processed in the background
sub = client.account.transfer_batch(
    [
        {"to_user_id": "5c3f6a1e-...", "amount": "50", "currency": "USDT"},
        {"to_user_id": "9d1e2b4c-...", "amount": "70", "currency": "USDT"},
    ],
    on_error="continue",
)
info = client.batches.info(sub.batch_id)   # progress and per-item results
```

Idempotency is the same ladder as on the other money endpoints: the
`Idempotency-Key` header (the SDK sends an auto uuid4, stable across retries; your own — the
`idempotency_key` kwarg), otherwise the gateway falls back to `order_id`, otherwise to the request signature.

## Custom checkout (v1.2.0)

Public (unsigned, key-free) invoice endpoints — for building **your own payment
page** instead of the gateway's hosted page: show the address/QR/amount, let the buyer pick a
currency, and poll the status straight from the browser.

```python
# invoice state (no merchant secret — safe to call from the browser)
state = client.payments.public_get(payment.uuid)          # GET /v1/pay/{id}
print(state.payment_status, state.address, state.amount_remaining)

# a currency-agnostic invoice (payment_status == "select"): the buyer picks a method
for m in state.accepted or []:                            # methods to choose from
    print(m.currency, m.network)
finalized = client.payments.public_select(payment.uuid,   # POST /v1/pay/{id}/select
                                          currency="USDT", network="tron")
print(finalized.address, finalized.payer_amount)          # rate locked, address allocated
```

`public_get` returns only buyer-facing fields (no `additional_data` or
`payer_email`); `public_select` locks the rate, allocates a deposit address, and moves the
invoice from `select` to `created`. The same public family as `payment_links.public_get` /
`checkout` and `payout_links.claim*`.

## Method overview

```python
# Payments
client.payments.create(amount=..., currency=..., order_id=..., ...)
client.payments.create_batch([...], on_error="continue")
client.payments.info(order_id="order-1")
client.payments.history(limit=25, offset=0, status="paid")
client.payments.services()
client.payments.qr(order_id="order-1")
client.payments.resend(order_id="order-1")
client.payments.refund(order_id="order-1", amount="10")   # address optional (except UTXO)
client.payments.refund_batch([...])                        # canonical (client.refunds is deprecated)
client.payments.resolve(uuid=..., action="accept" | "refund")
client.payments.send_email(uuid=..., email=...)
client.payments.set_accepted([...]) / list_accepted()
client.payments.set_discount(...) / list_discounts()
client.payments.set_accuracy(...) / get_accuracy()
client.payments.set_autorefund(...) / get_autorefund()
client.payments.public_get(payment_id)                     # public, unsigned — custom checkout
client.payments.public_select(payment_id, currency=..., network=...)   # public, unsigned

# Batch refunds — canonical payments.refund_batch (see client.refunds above)
client.payments.refund_batch([...], on_error="continue")

# Payouts
client.payouts.create(amount=..., currency=..., address=..., order_id=...)
client.payouts.create_mass([...])
client.payouts.create_batch([...], on_error="continue")
client.payouts.info(order_id="payout-1")
client.payouts.history(...)
client.payouts.services()
client.payouts.calculate(...)
client.payouts.approve(uuid)                     # repeat → 409 payout.not_pending = "already approved"
client.payouts.refund(...)
client.payouts.get_fee_config() / set_fee_config(bool)
client.payouts.get_refund_fee_config() / set_refund_fee_config(bool)

# Batches
client.batches.info(batch_id, limit=100, offset=0)

# Payment links (canonical payment_links; client.links is a documented alias)
client.payment_links.create(...) / list() / info(link_id) / toggle(link_id, active)
client.payment_links.public_get(link_id) / checkout(link_id, ...)   # public, unsigned

# Payout links (crypto checks)
client.payout_links.create(...) / create_batch([...]) / list() / info(link_id) / cancel(link_id)
client.payout_links.claim_info(token) / claim(token, address=...)   # public, unsigned

# Splits
client.splits.create_rule(...) / split_to_address(...) / split_to_merchant(...)
client.splits.list_rules() / delete_rule(rule_id) / get_config() / set_config(refund_hold_hours=...)

# Wallets
client.wallets.create(currency="USDT", network="tron", order_id="client-42")
client.wallets.block(address="T...")
client.wallets.blocked_address_refund(uuid="...", address="T...")   # once-only on the gateway: a repeat
                                                                    # returns the SAME payout
client.wallets.qr("T...")

# Account
client.account.balance()
client.account.referral()
client.account.transfer_to_personal(amount="50", currency="USDT")
client.account.transfer_to_user(to_user_id="...", amount="50", currency="USDT")  # UUID, not username
client.account.transfer_batch([...], on_error="continue")  # results — batches.info(batch_id)
client.account.vrcs(enabled=True)

# Webhooks
client.webhooks.register("https://...")   # UPSERT of the project's single endpoint:
                                         # .secret — the secret FOR VERIFYING webhook signatures
client.webhooks.deliveries()
client.webhooks.test_payment(url_callback="https://...")

# Settings
client.settings.list_auto_withdraw() / set_auto_withdraw(...) / delete_auto_withdraw(currency)
client.settings.list_allowlist() / add_allowlist(cidr) / remove_allowlist(cidr) / enable_allowlist(bool)

# Rates (public, no key)
client.rates.list("ETH")

# Sandbox (test key test_… ONLY — see the section above)
client.sandbox.simulate_deposit(invoice_id=..., amount=None, confirmations=None, txid=None)
client.sandbox.faucet(asset="USDT", amount="1000")
client.sandbox.reset()                        # created/select invoices only + balance zeroing
client.sandbox.list_webhooks()                # → [SandboxDelivery], the identifier is in .id
client.sandbox.replay_webhook(d.id)           # .id from list_webhooks() is the delivery_id
```

The async client has the same methods — with `await`.

## Notes

- **Amounts are strings** in currency units (`"25.00"`), not numbers. That preserves precision.
- **`order_id` is your business identifier**, the one you use to find a payment via
  `payments.info`. As of v1.1.0 the SDK does NOT fill it in: duplicates are prevented by the
  `Idempotency-Key` header (automatic, or via the `idempotency_key` kwarg). For payouts `order_id`
  is required.
- **The secret belongs on the server only.** The SDK is server-side; do not embed the key in client apps.
  The exception is the public methods (`payout_links.claim*`, `payment_links.public_get/checkout`,
  `payments.public_get/public_select`, `rates.*`): they are unsigned and need no keys.
- **Models ignore undocumented fields** — extra fields in an API response will not break parsing.
- **Create-method field names are validated.** A typo in a field name is a `TypeError` before
  the request is sent, not a silently altered money operation. See "Field name validation".

## License

MIT
