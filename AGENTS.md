# Oblodai Python SDK — guide for coding agents

Package `oblodai` (1.3). Everything below is verified against the gateway's contract snapshot in
`contract/contract.json` in the repository (`contract/` also holds golden response bodies, error
samples and real signed webhook deliveries).

## Non-negotiables

- Amounts are decimal **strings**: `"amount": "25"`, never `25`. Do not `float()` them; use
  `add_amounts` / `compare_amounts` from `oblodai`. A `Decimal` is accepted and sent as its exact
  string; a `float` in a request body raises `ConfigError` `sdk.float_amount` before any request.
- Request fields are **keyword arguments with the wire's own snake_case names**
  (`payments.create(amount="25", currency="USDT")`); a request model (`PaymentRequest`, …) or a
  plain dict as the first argument works too. Responses are frozen dataclasses generated from the
  gateway's OpenAPI contract (`oblodai.generated`): `invoice.url`, not `invoice["url"]`; fields the
  SDK does not know yet land in `.extra`.
- Every method's trailing keyword arguments are the same five (`oblodai.RequestOptions`):
  `idempotency_key`, `timeout` (seconds, per attempt), `max_retries`, `extra_headers` (this call
  only), `request_id` (sent as `X-Request-ID`; a uuid4 when omitted). Anything else raises
  `TypeError` before a request is sent (list methods also accept `limit=` / `offset=`).
- **One API key.** `public_id` + `secret` (or `OBLODAI_PUBLIC_ID` / `OBLODAI_SECRET`) sign every
  route with `ROUTES[key].auth == "key"` — money-in and money-out alike. `auth == "public"` means
  no credentials at all, `auth == "onboard"` means `X-Admin-Token` (`admin_token`), and that token
  goes on `merchants.*` and nowhere else. There is no second pair to configure and no per-call
  key selection.
- List methods return a lazy `Page`: `.first()` = one page (`.items`, `.paginate`, `.total`,
  `.has_pages`), iteration = every item, `.all(max_items=…)` = a list. Nothing is requested until
  the result is consumed. On `AsyncOblodai` it is awaited or walked with `async for`.
- Idempotency keys are generated automatically on create routes and reused across retries. Passing
  `idempotency_key` to a route the gateway does not deduplicate raises `sdk.idempotency_unsupported`
  — list methods included, where it is refused rather than dropped.
- Retry safety is `ROUTES[key].safe`, the gateway's own read-only classification. Nothing in the SDK
  guesses it from a path.
- Amounts never go through `float()` and never through `<` (`"10" < "9"` is `True` for strings);
  `compare_amounts` is the only correct ordering, and a non-decimal string raises `AmountError`.
- Environment, in full: `OBLODAI_PUBLIC_ID`, `OBLODAI_SECRET`, `OBLODAI_ADMIN_TOKEN`,
  `OBLODAI_BASE_URL`, `OBLODAI_LOG`, `OBLODAI_ALLOW_INSECURE`. Six variables, nothing else.

## Naming

| intent            | call |
| ----------------- | ---- |
| fetch one         | `.info(uuid \| {"order_id": …})` (alias `.get`) |
| fetch many        | `.history(params)` on payments/payouts (alias `.list`), `.list(params)` elsewhere |
| create            | `.create(params)`; webhooks: `.register(url)` |
| many, synchronous | `payouts.mass`, `payout_links.batch` — <=100, per-element `{"idx", "ok", "result", "message"}` |
| many, async       | `payments.batch`, `payouts.batch`, `refunds.batch`, `transfers.batch` — <=5000, poll `batches.info` |
| documents         | `documents.*_report / statement / fee_schedule / balance_certificate` → `FileResult(content, content_type, filename)` |
| provisioning      | `merchants.create({"email", "name"})`, `merchants.create_sandbox(merchant_id)` — unsigned; `admin_token` on self-hosted gateways |
| payer-facing      | `payments.public_view/select/public_qr`, `payment_links.public_view/checkout`, `payout_links.claim_preview/claim` — no credentials |

## Errors

`except OblodaiError as err` → `err.code` (`family.reason`), `err.http_status`, `err.retryable`
(authoritative — the SDK already retried what it should), `err.retry_after`, `err.request_id`
(quote it to support), `err.field` (400s), `err.synthetic` (a proxy answered, not the API).
Subclasses: `ValidationError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403,
`NotFoundError` 404, `ConflictError`/`IdempotencyConflictError` 409, `RateLimitError` 429,
`UnavailableError` 503, `InternalError` other 5xx, `TransportError` (no response),
`ConfigError` (before sending: `sdk.bad_config`, `sdk.bad_header`, `sdk.bad_amount`,
`sdk.bad_idempotency_key`, `sdk.idempotency_unsupported`, `sdk.missing_credentials`),
`ResponseTooLargeError` (`sdk.response_too_large`), `SignatureError` (webhook not from the gateway),
`WebhookPayloadError` (authentic delivery, unusable body — `webhook.bad_payload`),
`AmountError` (money helpers). `err.to_dict()` is log-safe.

Codes worth handling: `payout.insufficient_funds` (retryable), `payout.funds_maturing` (retryable),
`idempotency.key_reused`, `invoice.not_payable`, `payment.not_found`,
`merchant.bad_signature`, `request.rate_limited`. Full list: `oblodai.ERROR_CODES`.

## Statuses

- Payment: `select → created → confirm_check → paid | paid_over | wrong_amount | expired | cancelled`.
  `is_payment_paid` = paid/paid_over. `wrong_amount` needs `refunds.resolve({"uuid", "action"})`.
- Payout: `pending → approved → awaiting_cosign → broadcasting → sent → confirmed | failed | cancelled`.
- Webhook event types: `invoice.<status>`, `payout.<status>`, `wallet.paid`; the body's `type` is
  `"payment" | "payout" | "wallet"`.

## Webhooks

```python
from oblodai import webhooks

delivery = webhooks.verify_delivery(raw_body, request.headers, secret=secret)
```

`SignatureError` = not from the gateway (answer 401). `WebhookPayloadError` = authentic but
unusable (answer 400; retrying cannot fix it). An empty `secret` or a negative `tolerance_sec` is a
`ConfigError` before any crypto runs. An unknown event `type` is returned, not refused:
`webhooks.parse` yields `AnyWebhookEvent`, and `webhooks.is_known_event(event)` narrows it to the
three kinds this snapshot declares.

Verify over the **raw** bytes. `delivery.is_test` (also `webhooks.is_test_event(event)`) is true for
rehearsal deliveries (`test: true` in the signed body, `X-Webhook-Test: true`) — never treat them as
money. Deduplicate on `delivery.id` (`X-Webhook-Id`); drop out-of-order events with
`webhooks.is_stale(event, last_sequence)`. During a rotation pass `previous_secret=` for at least
26 h.

## Machine-readable surface

`ROUTES` (120 routes keyed by `operationId`: `method`, `path`, `auth`, `idempotent`, `safe`,
`bare`, `list_kind`), a model per request and response body, and the enums (`ErrorCode` (450),
`PaymentStatus`, `PayoutStatus`, `WebhookEventName`, …) — all generated into `oblodai.generated`
from the gateway's `openapi.json` (`names.lock` pins the public method names). In the repository
and the sdist, not in the installed wheel, `contract/` keeps golden response bodies per route,
error samples and signed webhook samples; `tests/contract/` checks the generated models against
them.
