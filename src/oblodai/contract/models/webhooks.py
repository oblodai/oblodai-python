"""Webhook endpoints, delivery records, test results and the event bodies the core signs."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple, TypedDict, Union

from ..enums import DeliveryStatus, FeeBearerResult, PaymentStatus, PayoutStatus
from .common import Money, Timestamp


class _WebhookEndpointRequired(TypedDict):
    #: Endpoint id.
    endpoint_id: str
    #: Registered callback URL.
    url: str


class WebhookEndpoint(_WebhookEndpointRequired, total=False):
    """`POST /v1/webhooks`."""

    #: The secret is shown ONCE — save it so you can verify callback signatures. Absent when only
    #: the URL was changed.
    secret: str


WEBHOOK_ENDPOINT_KEYS: Tuple[str, ...] = ("endpoint_id", "url", "secret")


class WebhookSecretRotated(TypedDict):
    """`POST /v1/webhooks/rotate-secret`."""

    #: Endpoint id.
    endpoint_id: str
    #: Registered callback URL.
    url: str
    #: New signing secret — shown only here.
    secret: str
    #: Until this moment deliveries are additionally signed with the old secret
    #: (X-Webhook-Signature-Prev).
    previous_secret_valid_until: Timestamp


WEBHOOK_SECRET_ROTATED_KEYS: Tuple[str, ...] = (
    "endpoint_id",
    "url",
    "secret",
    "previous_secret_valid_until",
)


class _WebhookDeliveryRequired(TypedDict):
    #: Delivery id (use it in `/v1/sandbox/webhooks/replay`).
    id: str
    #: URL the event was posted to.
    url: str
    #: Event that was delivered. Vocabulary: `EventType`.
    event_type: str
    status: DeliveryStatus
    #: How many attempts have been made.
    attempts: int
    #: Error of the last failed attempt, empty when it succeeded.
    last_error: str
    created_at: Timestamp
    updated_at: Timestamp


class WebhookDelivery(_WebhookDeliveryRequired, total=False):
    """Item of `/v1/webhooks/deliveries` and `GET /v1/sandbox/webhooks` (which adds `payload`,
    drops `sequence`)."""

    #: Global, increasing sequence of the delivered event.
    sequence: int
    #: The event body as it was posted (`GET /v1/sandbox/webhooks` only).
    payload: Dict[str, Any]


WEBHOOK_DELIVERY_KEYS: Tuple[str, ...] = (
    "id",
    "url",
    "event_type",
    "status",
    "attempts",
    "last_error",
    "sequence",
    "created_at",
    "updated_at",
)


class _WebhookTestResultRequired(TypedDict):
    #: true — the receiver answered 2xx.
    ok: bool
    #: true — the probe carried a signature.
    signed: bool


class WebhookTestResult(_WebhookTestResultRequired, total=False):
    """`/v1/test-webhook/*` and `/v1/payment/testing-webhook`."""

    #: Absent when the receiver could not be reached (see `error`).
    status_code: int
    #: Why the probe failed, when it did.
    error: str
    #: `/v1/payment/testing-webhook` only.
    url: str
    #: How long the probe took, in milliseconds.
    duration_ms: int


WEBHOOK_TEST_RESULT_KEYS: Tuple[str, ...] = ("ok", "signed", "status_code")


class _EventOptional(TypedDict, total=False):
    """Fields an event may carry."""

    #: Present and true ONLY on rehearsal deliveries (`webhooks.test`, sandbox). The body is signed
    #: like a live one, so a handler must check this flag (or `X-Webhook-Test`) and never act on a
    #: test event as if money moved.
    test: bool


class _EventBase(_EventOptional):
    """Fields every delivered event carries."""

    uuid: str
    #: Null on refund payouts.
    order_id: Optional[str]
    is_final: bool
    #: When the state change was committed — order events by this, or by `sequence`.
    event_at: Timestamp
    #: Global, increasing (gaps are normal); a lower sequence arriving later is stale.
    sequence: int
    txid: str


class PaymentEvent(_EventBase):
    """`invoice.<status>` — an invoice changed state."""

    type: Literal["payment"]
    status: PaymentStatus
    amount: Money
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    payer_amount: Money
    payer_currency: str
    #: What actually landed on the address, in `payer_currency`.
    payment_amount: Money
    payer_address: str
    payer_address_is_refundable: bool
    additional_data: str


PAYMENT_EVENT_KEYS: Tuple[str, ...] = (
    "type",
    "uuid",
    "order_id",
    "status",
    "is_final",
    "amount",
    "currency",
    "network",
    "payer_amount",
    "payer_currency",
    "payment_amount",
    "payer_address",
    "payer_address_is_refundable",
    "additional_data",
    "txid",
    "event_at",
    "sequence",
)


class PayoutEvent(_EventOptional):
    """`payout.<status>` — a payout (or refund) changed state; the body is the payout itself
    (without `error`/`error_code`/`wallet_uuid`) plus `event_at` and `sequence`."""

    type: Literal["payout"]
    #: Payout id.
    uuid: str
    #: Your payout number (reference). Null for a refund.
    order_id: Optional[str]
    status: PayoutStatus
    #: true — the status is final (paid / fail / cancel).
    is_final: bool
    #: Payout amount in currency, debited from your balance.
    amount: Money
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: Recipient address.
    address: str
    #: Destination tag/memo passed at creation. Empty — no memo.
    memo: str
    #: How much actually goes to the recipient's address: amount − commission.
    payer_amount: Money
    #: Network fee withheld, in the payout currency. 0 — the gateway absorbed the fee.
    commission: Money
    #: Who paid the network fee: gateway | merchant | recipient.
    fee_bearer: FeeBearerResult
    #: api (via the integration) | manual (from the cabinet).
    source: str
    #: true — the payout is awaiting approval (always false for an API key).
    approval_required: bool
    #: true — this is a payment refund, not a regular payout.
    is_refund: bool
    #: Id of the payment being refunded (null if this is not a refund).
    refund_for: Optional[str]
    #: Your order_id of the payment the refund was made for (null for a regular payout).
    payment_order_id: Optional[str]
    #: On-chain transaction hash (appears after sending).
    txid: str
    #: Signed link to the PDF cheque for this operation.
    document_url: str
    created_at: Timestamp
    updated_at: Timestamp
    #: When the state change was committed — order events by this, or by `sequence`.
    event_at: Timestamp
    #: Global, increasing (gaps are normal); a lower sequence arriving later is stale.
    sequence: int


PAYOUT_EVENT_KEYS: Tuple[str, ...] = (
    "type",
    "uuid",
    "order_id",
    "status",
    "is_final",
    "amount",
    "currency",
    "network",
    "address",
    "memo",
    "payer_amount",
    "commission",
    "fee_bearer",
    "source",
    "approval_required",
    "is_refund",
    "refund_for",
    "payment_order_id",
    "txid",
    "document_url",
    "created_at",
    "updated_at",
    "event_at",
    "sequence",
)


class WalletEvent(_EventBase):
    """`wallet.paid` — a deposit landed on a static wallet."""

    type: Literal["wallet"]
    status: Literal["paid"]
    #: The static wallet address the deposit landed on.
    address: str
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    payer_currency: str
    #: What actually landed on the address, in `payer_currency`.
    payment_amount: Money


WALLET_EVENT_KEYS: Tuple[str, ...] = (
    "type",
    "uuid",
    "order_id",
    "status",
    "is_final",
    "address",
    "currency",
    "network",
    "payer_currency",
    "payment_amount",
    "txid",
    "event_at",
    "sequence",
)

#: Any body the core signs and posts; switch on `type` to narrow it.
WebhookEvent = Union[PaymentEvent, PayoutEvent, WalletEvent]
