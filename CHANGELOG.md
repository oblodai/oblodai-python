# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.0] — 2026-09-25

Generated from the gateway's OpenAPI contract by the backend's `tools/sdkgen`. Breaking: every
method name follows `client.<resource>.<method>` from the contract's tags and operation ids, and
results are typed models instead of dicts — see [MIGRATION-2.0.md](MIGRATION-2.0.md) for the full
old-to-new table.

### Added

- Typed models for every request and response (frozen dataclasses): money is `Decimal`, enums are
  `str` enums; an unknown enum value stays a plain string and an unknown field lands in `.extra`,
  so a newer gateway never breaks parsing.
- Bodies as keyword arguments, as a wire-shaped mapping or as a request model. A field given both
  in the mapping (or model) and as a keyword — the sandbox faucet's `idempotency_key` too — is
  `ConfigError` `sdk.bad_config` before anything is sent, as in every Oblodai SDK.
- `names.lock`: the public method names are pinned; the generator refuses to drop or rename one.
- Explicit per-call options (`oblodai.RequestOptions`): `idempotency_key`, `timeout` (seconds),
  `max_retries`, `extra_headers`, `request_id`; every request carries an `X-Request-ID`.
- `client.with_options(...)`, `resource.with_raw_response.<method>(...)` (`RawAPIResponse`) and
  request/response `Hooks`.
- `Page.by_page()` — page by page, one request per page.
- Long-running operations (batches, document exports) return a `Job` with `wait()`; which calls
  are long-running, what to poll and which statuses end the wait come from the contract's
  `x-sdk-poll` (`oblodai.lro`, generated), each job waiting for its own terminal statuses.
- `webhooks.to_model(event)`, `webhooks.WEBHOOK_MODELS` (kind → model),
  `webhooks.WEBHOOK_EVENTS` (event name → kind) and `webhooks.WEBHOOK_ID_FIELDS` (kind → the body
  field holding the object's id, read by `webhooks.object_id(event)`), generated from the
  contract's webhooks. `webhooks.parse` requires only `type` of a kind it does not know.
- The README method table is generated from the contract (between `sdkgen:methods` markers), and
  the generator adds new method names to `names.lock` itself; `names.2.0.txt` freezes the names
  2.0 shipped with, which `MIGRATION-2.0.md` maps.
- The signing protocol comes from the contract's `x-oblodai-signing` (`oblodai.generated.signing`,
  generated): the signed-request and webhook header names, the canonical strings, the clock skew
  (`SIGNATURE_SKEW_SECONDS`, the default `tolerance_sec` of `webhooks.verify`), `MAX_BODY` and
  `MAX_IDEMPOTENCY_KEY_LENGTH`. The public `HEADER_*` names of `oblodai.core.signing` and
  `oblodai.webhooks` stay, as aliases of the generated values (the rehearsal header
  `HEADER_WEBHOOK_TEST` too, from `x-oblodai-signing.webhook.test_header`); a header the gateway renames
  reaches the SDK by regeneration alone, and the conformance suite checks the headers a signed
  request actually carries against the contract's names.
- `str(err)` reads well in a log line: `[code] message (request_id=…)`.
- The shared conformance suite (`tests/conformance`) every Oblodai SDK runs: signing and webhook
  vectors read from the contract's `x-oblodai-signing`, retries and idempotency keys, `Retry-After`,
  `409 idempotency.in_progress`, float amounts, forward compatibility.
- Every code block of both READMEs runs in the test suite against a mock gateway.

### Changed

- Python 3.10 or newer (was 3.9).
- Whether a POST may be re-sent without a key comes from the contract's `x-retry-safe`, not from a
  table in the SDK.
- `ROUTES` is keyed by `operationId`.
- The status classes behind `is_payment_final`, `is_payment_paid`, `is_payout_final`,
  `is_payout_succeeded` and `FINAL_PAYMENT_STATUSES` / `FINAL_PAYOUT_STATUSES` (now in enum order)
  come from the contract's `x-status-classes`; `webhooks.KNOWN_EVENT_KINDS` from its webhooks (it
  now knows `conversion`); the float allowance `NON_MONEY_NUMBERS` from its `number` fields.
- Timeouts are in seconds: `timeout_ms` became `timeout`, the client's `deadline_ms` became
  `deadline`; per-call `headers` became `extra_headers`.
- A `float` anywhere in a request body is a `ConfigError` (`sdk.float_amount`) before anything is
  sent.

### Removed

- `merchants.create` — `POST /v1/merchants` is not part of the merchant API contract.
  `merchants.create_sandbox` is `sandbox.onboard_store`.
- `webhooks.test(kind, …)` — one method per kind: `webhooks.send_test_payment` and its siblings.
- The hand-written resources and the per-call `deadline_ms`.
- `contract/contract.json` (the 1.3 snapshot) and `CONTRACT_CORE_COMMIT` / `CONTRACT_EXPORTED_AT`,
  which described it. `CONTRACT_HASH` (sha256 of `openapi.json`, in the User-Agent) and the new
  `CONTRACT_VERSION` are generated with the code.

### Fixed

- A conversion delivery (`conversion.completed` / `conversion.refunded`, identified by `id`, not
  `uuid`) is no longer refused as `webhook.bad_payload`, and `webhooks.is_known_event` recognises
  it.

## [1.3.0] — 2026-08-26

Rewrite generated from the gateway's contract snapshot. The 1.x line signed four fields and got a
401 from the current gateway on every call; nothing of it is left. Upgrading from 1.2 is a rewrite
of the calling code too — see [MIGRATION-1.3.md](MIGRATION-1.3.md).

### Added

- Every merchant route (107) — cancel/validate, batches, documents, fee configs, split opt-in,
  secret rotation, payer-facing checkout and claim endpoints, merchant provisioning.
- A `merchants` namespace for platforms that onboard merchants themselves
  (`merchants.create`, `merchants.create_sandbox`). These routes are unsigned; a self-hosted
  gateway gates them with the `admin_token` client option (`OBLODAI_ADMIN_TOKEN`), which is sent
  as `X-Admin-Token` on those routes and on no others.
- An asynchronous client (`from oblodai.aio import AsyncOblodai`) beside the synchronous one. Both
  drive the same I/O-free core: signing, envelope decoding, the retry decision, idempotency and
  clock-skew correction are shared code, so the two clients cannot drift apart.
- Lazy `Page` lists — `.first()` for one page, iteration for every page, `.all(max_items=…)` to
  collect; nothing is requested until the result is consumed.
- Retries driven by the gateway's own `retryable` flag; transport failures and envelope-less proxy
  answers are re-sent only when repeating is safe. Per-attempt `timeout_ms` and a whole-call
  `deadline_ms`; `Retry-After` wins over the backoff.
- Automatic idempotency keys on create routes, reused across that call's retries.
- Clock-skew correction: a 401 `merchant.bad_signature`/`auth.bad_timestamp` re-signs once with
  the server's `Date`, and the offset is kept only if that attempt got past authentication.
- One API key: `public_id` + `secret` sign every route the gateway gates (`auth == "key"`),
  money-in and money-out alike. The payout credential pair (`payout_public_id` /
  `payout_secret`, `OBLODAI_PAYOUT_PUBLIC_ID` / `OBLODAI_PAYOUT_SECRET`) and the
  `prefer_payout_key` per-call option are gone, as is the `batches.info` retry with a second key;
  onboarding returns a single `api_key`. `merchant.wrong_key_kind` has left the error catalogue —
  the gateway raises it only for a legacy `oblodai_pk_…` / `oblodai_wk_…` pair.
- `oblodai.webhooks` — `verify`, `verify_delivery`, `parse`, `is_stale`, `is_test_event`: raw-byte
  verification, rotation-aware (`previous_secret`, `X-Webhook-Signature-Prev`), no client needed.
  Accepts any header shape (`dict`, `email.message.Message`, `httpx.Headers`, ASGI pairs).
- Rehearsal deliveries (`webhooks.test`, sandbox) are marked: `delivery.is_test` and
  `webhooks.is_test_event(event)` are true for them. They are signed exactly like live ones, so a
  handler must check this and never treat one as money.
- `WebhookPayloadError` (code `webhook.bad_payload`) for a delivery whose signature verified but
  whose body is unusable. It is a `ContractError`, deliberately not a `SignatureError`: a receiver
  that answers 401 to signature failures must not answer 401 to an authentic delivery.
- `AmountError` (code `sdk.bad_amount`) from the money helpers; it is also a `ValueError`, so
  existing `except ValueError` keeps working.
- `ResponseTooLargeError` (code `sdk.response_too_large`) when a response passes the size cap.
- `AnyWebhookEvent` = `WebhookEvent | UnknownWebhookEvent` and `webhooks.is_known_event()`: an
  event kind newer than this snapshot is returned with its raw `type`, and narrowed explicitly.
- A per-call `headers=` option on every method, merged over the client's own headers and subject
  to the same reserved-name and value checks.
- `oblodai.__version__` beside `SDK_VERSION`, both read from the installed distribution's
  metadata, so `pyproject.toml` is the only place a version is written.
- `contract/` ships the gateway's export (routes, schemas, enums, 469 error codes, signing
  vectors, golden bodies, real signed webhook deliveries). `scripts/codegen.py` generates the
  route registry, enums, error codes and request `TypedDict`s; `scripts/gen_async.py` mirrors the
  resource layer for the async client; `scripts/check_drift.py` fails CI when either is stale.
- Three test tiers — unit (signing and webhook vectors, retry/idempotency/skew/URL rules, the
  transport's limits), contract (every route hits the right method, path, auth and idempotency
  header; every `RouteSpec` field equals the contract; every golden body matches its model
  key-for-key) and live (a real gateway).

### Changed

- Requests are signed with the five-field recipe
  (`ts\nMETHOD\nrequest_uri\nidempotency_key\nbody`) over path + raw query, with an EMPTY
  idempotency slot when no key is sent. 1.x returned 401 on every call.
- Models, statuses, pagination and parameter names match the current API vocabulary; field names
  are exactly the wire's `snake_case`, amounts are decimal strings everywhere.
- Retry safety now comes from the contract's own `safe` flag, hand-classified by the core per
  route, instead of a path-suffix heuristic in the code generator. The generator refuses to run
  against a snapshot that does not declare it.
- `PermissionError` is now `PermissionDeniedError`. The old name shadowed the builtin and is kept
  as an unexported alias.
- `PaymentHistoryBody` no longer offers `kind`: the core's shared DTO carries it, but its own
  description says it applies to `/v1/payout/history` only.
- `documents.download` requires `exp` and `sig` — the two halves of a `document_url` signature.
  A link without them is not downloadable, and that is now a `ConfigError` rather than a 403.
- `httpx` is the only runtime dependency (`pydantic` is gone), pinned `>=0.24,<1.0`; Python >=
  3.9; the package ships `py.typed` and passes `mypy --strict`.
- `client.payment_links` / `client.payout_links` are the namespace names, and every method is
  `snake_case` (`send_email`, `rotate_secret`, `create_sandbox`, `refund_blocked_deposit`, …).
- The money-moving methods document the error codes worth branching on, and a contract test keeps
  those lists inside the gateway's own catalogue.

### Fixed

- The per-attempt timeout now covers the WHOLE response read, not just the first byte. `httpx`
  times out per socket operation, so a server dribbling one byte at a time held a call open long
  past its `timeout_ms`.
- Response bodies are read under a size cap (8 MiB on envelope routes, 64 MiB on document routes)
  and fail with `ResponseTooLargeError` instead of exhausting memory.
- A deeply nested JSON body raises the SDK's own error instead of letting `RecursionError` escape
  — in the envelope decoder and in webhook parsing, where the bytes are attacker-controlled.
- `retry_after` of any JSON type is coerced or dropped; a boolean, a string or a huge number no
  longer raises a `TypeError` in the middle of the retry loop. `Retry-After` headers are clamped
  the same way: never negative, and never past 86 400 s. The delay actually slept is capped much
  lower, by `RetryOptions.max_retry_after_ms`.
- The error envelope is decoded field by field. One field of the wrong type no longer discards the
  rest, and `retryable` is believed only when it is a literal boolean.
- Webhook verification checks the MAC BEFORE the freshness window, so the timestamp error is no
  longer an oracle for an unauthenticated caller. An empty `secret` (or an empty
  `previous_secret`) is a `ConfigError` before any crypto runs, and a negative `tolerance_sec` is
  a `ConfigError` rather than a wider window.
- An unknown webhook event `type` is returned with its raw string instead of raising; a receiver
  written against an older SDK still sees the delivery.
- `webhooks.is_stale` returns `False` for an event with a missing or non-integer `sequence` and
  never raises. It used to return `True` for a missing one — which SKIPPED the delivery.
- Signature headers are trimmed, accepted in either hex case, and rejected with an `0x` prefix.
  Timestamp headers are read as ASCII digits only (`int("١٢٣")` used to parse).
- Secrets never render: `Credentials`, `EngineSettings` and the client redact in `repr()`, and
  fields are redacted before they reach a caller-injected logger, not only the built-in one.
- The money helpers accept ASCII digits only (`\d` also matched Arabic-Indic digits), cap the
  input length, and raise `AmountError` instead of a bare `ValueError`.
- Request bodies are serialized with `allow_nan=False`, and a `Decimal` is rendered as the wire's
  own decimal string. A `float("nan")` used to be encoded as the bare token `NaN`, which is not
  JSON.
- A caller-supplied `idempotency_key` that fails validation is now a `ConfigError`
  (`sdk.bad_idempotency_key`) rather than a 400-family `ValidationError`: nothing was sent.
- Caller headers can no longer take over a header the SDK owns (`Accept`, `Content-Type`,
  `User-Agent`, `X-Public-Id`, `X-Signature`, `X-Timestamp`, `Idempotency-Key`, `X-Admin-Token`),
  compared case-insensitively, and a value carrying CR/LF or non-ASCII bytes is a `ConfigError`.
- A redirect is never followed. If an injected HTTP client follows one, the SDK notices the answer
  came from a URL nobody asked for and raises the "unexpected redirect" error.
- Clock-skew correction is concurrency-safe: the offset is compared against what the attempt was
  signed with, guarded by a lock, and reverted only if this call's correction is still in force.
- A caller `idempotency_key` on a list method raises `sdk.idempotency_unsupported` instead of
  being dropped silently.
- `TransportError` no longer assigns `__cause__ = None`, which suppressed the original traceback.
- The transport no longer catches every exception as `transport.network`; an SDK error raised
  during the read keeps its own (non-retryable) identity.

### Removed

- `**kwargs` field whitelists on create methods — bodies are dicts typed by the generated
  `TypedDict`s, so a typo is caught by the type checker instead of a hand-kept list.

### Packaging and CI

- The drift check regenerates into a temporary directory and compares, so it is non-destructive
  and works on a clean checkout; both generators find `ruff` on `PATH` instead of assuming a
  repository-local virtualenv.
- The sdist carries `contract/`, `examples/`, `AGENTS.md` and `MIGRATION-1.3.md`; the wheel
  carries `AGENTS.md` as `oblodai/AGENTS.md`. CI asserts all of it.
- The release workflow re-runs every CI gate before uploading, fires only on a `vX.Y.Z` tag,
  checks the tag against the packaged version, and publishes with `twine` and an API token.

## Earlier releases

The entries below summarise the 1.0–1.2 line. They describe an implementation 1.3.0 replaced
wholesale; nothing in them still applies to the current package.

## [1.2.1] — unreleased, superseded by 1.3.0

- Added: field-name checking on the create methods. They took fields as `**kwargs` and put them
  into the signed body, so an unknown name was silently ignored by the gateway and the operation
  ran with a DIFFERENT meaning while the response looked fine — a typo in `amount` changed both
  the sum and the invoice lifetime. Names were checked against a whitelist and an unknown one
  raised `TypeError` before signing.
- Docs: payment and payout status tables in the README, checked against the core's own vocabulary.
- Docs: corrected the underpayment description. An underpaid invoice passes through
  `wrong_amount_waiting` (the buyer may still top it up) and only becomes `wrong_amount` after its
  lifetime expires; `resolve` accepts only the second state.
- Docs: warned that the webhook signing secret is the ENDPOINT secret from `register().secret`,
  not the API key secret, and that `register()` is an upsert of the project's single endpoint —
  calling it with a new URL redirects deliveries rather than adding a receiver.
- Docs: `payment.url` and `claim_url` are built from the gateway's public base URL and come back
  empty on a local stand without one.
- Docs: `sandbox.reset()` cancels invoices in `created`/`select` and zeroes balances; it
  deliberately leaves an invoice that already has a deposit alone.

## [1.2.0] — 2026-07-19

- Added: the developer sandbox namespace (`simulate_deposit`, `faucet`, `reset`, `list_webhooks`,
  `replay_webhook`), test keys only.
- Added: signed GET requests; internal transfers to a platform user (`transfer_to_user`,
  `transfer_batch`); the payer-facing invoice endpoints (`public_get`, `public_select`).
- Security: the base URL must be `https://`, checked when the client is built. It used to accept
  `http://` silently and send `X-Signature` in the clear. Loopback hosts stay allowed.
- Deprecated: `client.refunds` as a duplicate of `payments.refund_batch`.
- Changed: `Idempotency-Key` on the calls that reserve money (`payout_links.create`,
  `payout_links.create_batch`, `wallets.blocked_address_refund`), computed once before the retry
  loop. Without it a retry after a timeout could fund a second payout link.
- Fixed docs: a sandbox deposit with too few confirmations does not mature on its own; the ~10
  minute timer belongs to the payout maturity hold (`payout.funds_maturing`), which is terminal
  and not retried.

## [1.1.0] — 2026-07-15

- BREAKING: idempotency moved to the `Idempotency-Key` header. The SDK no longer substitutes an
  `order_id` of its own; set one explicitly if you relied on that.
- Added: batches (`payments.create_batch`, `refunds.create_batch`, `payouts.create_batch`, up to
  5000 elements) and `batches.info`.
- Added: payment links, payout links ("crypto cheques") with public claim endpoints, splits,
  invoice-by-email, and underpayment `resolve`.
- Changed: `address` is no longer required on `payments.refund` — the refund goes to the payer's
  address by default (UTXO networks still need one).

## [1.0.2] — 2026-07-12

- Fixed: an `order_id` of only whitespace is treated as absent for auto-idempotency; an empty key
  gives no deduplication on the gateway.

## [1.0.1] — 2026-07-12

- Fixed: auto-idempotency on `payments.create` and `account.transfer_to_personal`; without a key,
  a retry after a timeout could create a duplicate payment.
- Fixed: `Retry-After` is no longer clamped to the computed backoff maximum.
- Fixed: `payout.funds_maturing` is terminal and no longer retried automatically.
- Fixed: a non-ASCII signature header raises the SDK's signature error instead of a `TypeError`
  out of `hmac.compare_digest`.

## [1.0.0] — 2026-07-12

- First release of the official Python SDK: payments, payouts and mass payouts, static wallets,
  refunds, webhooks, public catalogues; HMAC-SHA256 request signing and constant-time webhook
  verification; `from_env()`; retries with exponential backoff honouring `Retry-After`.
