# Migrating to 1.3

1.3.0 is a rewrite generated from the gateway's own contract snapshot. The 1.0–1.2 line signed
four fields where the current gateway verifies five, so **every** call it makes returns
`401 merchant.bad_signature`. There is no compatibility shim: 1.2 code does not run against
today's gateway either way, and 1.3 is the working client.

This page lists what changes in your code, and the behaviour changes worth knowing about even if
you are already on a 1.3 pre-release.

## The shape of a call

```python
from oblodai import Oblodai

oblodai = Oblodai()  # OBLODAI_PUBLIC_ID / OBLODAI_SECRET / OBLODAI_BASE_URL

invoice = oblodai.payments.create(
    {"amount": "25", "currency": "USDT", "network": "tron", "order_id": "order-1001"}
)
print(invoice["url"], invoice["status"])
```

- Bodies are **dicts with the wire's own `snake_case` names**, not `**kwargs`. Every body has a
  `TypedDict` in `oblodai.contract.requests`, so a typo is a type error rather than a field the
  gateway silently ignores.
- Responses are dicts too: `invoice["url"]`, not `invoice.url`. Every response has a `TypedDict`
  in `oblodai.contract.models`.
- Amounts are decimal **strings** everywhere. Use `add_amounts` / `compare_amounts`; never
  `float()`, and never `<` on the raw strings (`"10" < "9"` is `True`).
- Every method takes the same five trailing keyword arguments: `idempotency_key`, `timeout_ms`
  (per attempt), `deadline_ms` (the whole call, retries included), `prefer_payout_key` and
  `headers` (extra headers for this call alone). List methods also take `limit=` / `offset=`.
  Anything else raises `TypeError` before a request is sent.

## Renames

| 1.2 | 1.3 |
| --- | --- |
| `PermissionError` | `PermissionDeniedError` (the old name shadowed the builtin; kept as an unexported alias) |
| `payments.public_get` | `payments.public_view` |
| `payments.public_select` | `payments.select` |
| `sandbox.simulate_deposit` | `sandbox.deposit` |
| `sandbox.list_webhooks` | `sandbox.webhooks` |
| `sandbox.replay_webhook` | `sandbox.replay` |
| `payout_links.claim_info` | `payout_links.claim_preview` |
| `wallets.blocked_address_refund` | `wallets.refund_blocked_deposit` |
| `account.transfer_to_user` / `transfer_batch` | `transfers.to_user` / `transfers.batch` |
| `payment_links.public_get` | `payment_links.public_view` |
| `payments.create_batch` | `payments.batch` |
| `payouts.create_batch` / `create_mass` | `payouts.batch` / `payouts.mass` |
| `client.links` | `client.payment_links` |
| `client.refunds.create_batch` | `refunds.batch` |

## New: the merchants namespace and the admin token

Platforms that onboard merchants themselves get `merchants.create({"email", "name"})` and
`merchants.create_sandbox(merchant_id)`. These routes are **not** HMAC-signed; a self-hosted
gateway gates them with an admin token:

```python
Oblodai(admin_token="…")  # or OBLODAI_ADMIN_TOKEN
```

The token is sent as `X-Admin-Token` on those routes **and on no others** — it gates the whole
gateway, so every merchant request that carried it would be a place it can leak.

## Webhooks

```python
from oblodai import SignatureError, WebhookPayloadError, webhooks

try:
    delivery = webhooks.verify_delivery(raw_body, request.headers, secret=endpoint_secret)
except SignatureError:
    return 401  # not from the gateway
except WebhookPayloadError:
    return 400  # authentic, but this receiver cannot read it - no retry will fix it
```

- **Rehearsal deliveries are flagged.** `webhooks.test(...)` and the sandbox send events signed
  exactly like live ones, with `test: true` in the body and `X-Webhook-Test: true` on the
  request. Check `delivery.is_test` (or `webhooks.is_test_event(event)`) and never act on one as
  if money moved.
- **`webhook.bad_payload` is a new error kind**, in the contract family rather than the signature
  family. A receiver that answers 401 to signature failures must not answer 401 to an authentic
  delivery it merely cannot parse — the gateway would retry it for 26 hours to no purpose.
- **The MAC is checked before the freshness window.** A wrong signature now always reports
  `webhook.bad_signature`, never `webhook.stale_timestamp`.
- **An empty `secret` is a `ConfigError`**, raised before any crypto. So is an empty
  `previous_secret` and a negative `tolerance_sec` (`0` still means "no freshness window").
- **`is_stale` never raises and never skips what it cannot judge.** An event with a missing or
  non-integer `sequence` is not stale. In earlier builds a missing `sequence` reported *stale*,
  which SKIPPED the delivery.
- **An unknown event `type` is returned, not refused**, with its raw string in `event["type"]`.
  `webhooks.parse` returns `AnyWebhookEvent` (`WebhookEvent | UnknownWebhookEvent`); narrow it
  with `webhooks.is_known_event(event)`.

## Retry safety comes from the contract

Whether a request may be re-sent after a transport failure is the `safe` flag the core publishes
per route, not a guess from the shape of the path. Nothing about this needs your attention except
the consequence: a write the gateway does not deduplicate is never automatically repeated once it
may have reached the gateway.

A caller `idempotency_key` on a route the gateway does not deduplicate raises
`sdk.idempotency_unsupported` — including on list methods, where it used to be dropped silently.

## Secrets do not print

`Credentials`, `EngineSettings` (reachable as `client.transport.settings`) and the client redact
in `repr()`, and log fields are redacted **before** they reach a logger you injected, not only the
built-in one. Secret-bearing response fields (`WebhookEndpoint.secret`,
`WebhookSecretRotated.secret`, `PayoutLink.passcode` / `claim_token` / `claim_url` — the claim URL
embeds the token) are plain dict entries —
they redact wherever the SDK logs them, but a `print(result)` of your own still shows them.

## Model corrections

- `PaymentHistoryBody` no longer offers `kind`. The core's shared DTO carries it, but its own
  description restricts it to `/v1/payout/history`.
- `documents.download(kind, id, query)` requires `exp` and `sig` in `query` — the two halves of a
  `document_url` signature. Without them the gateway answers 403; now it is a `ConfigError`
  before anything is sent.
- `ClaimResult.status` is the link's status (`claimed`), not the payout's.
- `wallet.blocked` is not an error code the gateway emits; branch on `wallet.abandoned` and
  `refund.nothing_to_refund` around `wallets.refund_blocked_deposit`.

## Limits worth re-checking

| operation | limit |
| --------- | ----- |
| `payouts.mass` | 100 elements, synchronous, per-element outcomes |
| `payout_links.batch` | 500 elements, synchronous, per-element outcomes |
| `payments.batch`, `payouts.batch`, `refunds.batch`, `transfers.batch` | 5000 elements, asynchronous, poll `batches.info` |
| envelope response body | 8 MiB, then `ResponseTooLargeError` (`sdk.response_too_large`) |
| document response body | 64 MiB, then `ResponseTooLargeError` |
| a `retry_after` the gateway reports | clamped to 86 400 s; the retry loop still sleeps at most `RetryOptions.max_retry_after_ms` |
| `Idempotency-Key` | 255 printable ASCII characters |
