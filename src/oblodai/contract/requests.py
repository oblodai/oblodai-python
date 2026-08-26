# GENERATED FILE - do not edit. Source: contract/contract.json (core 2cc44c16f516).
# Regenerate with: python scripts/codegen.py


"""Request bodies by route, generated from the core's documented DTOs
(field names, required flags, descriptions and examples)."""

from __future__ import annotations

from typing import List, Literal, Mapping, TypedDict

from .enums import (
    AmountModeArg,
    BatchOnErrorArg,
    FeeBearerArg,
    NetworkArg,
    PaymentStatusArg,
    PayoutStatusArg,
)
from .models.common import Money


class ApiAllowlistAddBody(TypedDict):
    """Request body of `POST /v1/api-allowlist/add`."""

    #: IP or subnet in CIDR notation (203.0.113.7 or 203.0.113.0/24). Example: "203.0.113.0/24".
    cidr: str


class ApiAllowlistEnableBody(TypedDict):
    """Request body of `POST /v1/api-allowlist/enable`."""

    #: true — accept API calls only from listed addresses; false — the list is kept but not
    #: enforced. Example: true.
    enabled: bool


class ApiAllowlistRemoveBody(TypedDict):
    """Request body of `POST /v1/api-allowlist/remove`."""

    #: IP or subnet in CIDR notation (203.0.113.7 or 203.0.113.0/24). Example: "203.0.113.0/24".
    cidr: str


class AutoWithdrawDeleteBody(TypedDict):
    """Request body of `POST /v1/auto-withdraw/delete`."""

    #: Asset whose auto-withdrawal to switch off. Example: "USDT".
    currency: str


class _AutoWithdrawSetBodyRequired(TypedDict):
    #: Destination address (the merchant's external wallet). Example:
    #: "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx".
    address: str
    #: Asset to withdraw automatically. Example: "USDT".
    currency: str
    #: Network of the destination address. Example: "tron".
    network: NetworkArg


class AutoWithdrawSetBody(_AutoWithdrawSetBodyRequired, total=False):
    """Request body of `POST /v1/auto-withdraw/set`."""

    #: Threshold: the sweep runs once the available balance of the asset reaches this amount; empty
    #: uses the network minimum. Example: "100".
    min_amount: Money


class _BatchInfoBodyRequired(TypedDict):
    #: Batch id from the submit response. Example: "9f4c1a2b-77de-4a55-9c1f-0e2b3d4a5f60".
    batch_id: str


class BatchInfoBody(_BatchInfoBodyRequired, total=False):
    """Request body of `POST /v1/batch/info`."""

    #: How many items to return in items (pagination). Example: 100.
    limit: int
    #: Offset over items. Example: 0.
    offset: int


class _ClaimTokenBodyRequired(TypedDict):
    #: Recipient address in the payout network.
    address: str


class ClaimTokenBody(_ClaimTokenBodyRequired, total=False):
    """Request body of `POST /v1/claim/{token}`."""

    #: Memo/tag — only for networks where it is required.
    memo: str
    #: Claim code — if the sender set one on the link. After 10 incorrect attempts the link is
    #: locked.
    passcode: str


class _DocumentsJobsBodyRequired(TypedDict):
    kind: str


_DocumentsJobsBodyOptional = TypedDict(
    "_DocumentsJobsBodyOptional",
    {
        # File format: pdf (default) or csv. CSV is generated without layout — cheaper for large
        # statements and loads into Excel/1C. Example: "csv".
        "format": str,
        # Start of the period, YYYY-MM-DD (defaults to the first day of the current month). Example:
        # "2025-01-01".
        "from": str,
        # Document language (default en). Example: "ru".
        "lang": str,
        # End of the period, inclusive, YYYY-MM-DD (defaults to today). The period may span up to two
        # years. Example: "2026-08-19".
        "to": str,
    },
    total=False,
)


class DocumentsJobsBody(_DocumentsJobsBodyRequired, _DocumentsJobsBodyOptional):
    """Request body of `POST /v1/documents/jobs`."""


class DocumentsJobsInfoBody(TypedDict):
    """Request body of `POST /v1/documents/jobs/info`."""

    #: Job id from the creation response.
    job_id: str


class ExchangeRateListBody(TypedDict, total=False):
    """Request body of `POST /v1/exchange-rate/list`."""

    #: Currency code. If set, only its rate is returned. If empty or the body is {}, rates for all
    #: currencies are returned. Example: "ETH".
    currency_from: str
    #: Quote currency: USDT by default; any pricing asset, including fiats with a direct feed (EUR,
    #: RUB, …).
    currency_to: str
    #: Page size, 1–100; default 25.
    limit: int
    #: Offset from the start of the list; default 0.
    offset: int


class LinkIdCheckoutBody(TypedDict, total=False):
    """Request body of `POST /v1/link/{id}/checkout`."""

    #: Amount entered by the buyer, in the link's price currency; required for open and range,
    #: ignored for fixed. Example: "10.00".
    amount: Money
    #: Settlement currency — the coin the buyer pays with; needed only if the link did not pin
    #: pinned_currency. Example: "USDT".
    currency: str
    #: Settlement network; needed only if the link did not pin pinned_network. Example: "tron".
    network: NetworkArg
    #: Shop order number from the embedded widget (data-oblodai-order-id); carried over to the
    #: invoice and to the webhook for matching with the order; not an idempotency key.
    order_id: str
    #: Buyer email — the cheque is sent there automatically after payment. Example:
    #: "buyer@example.com".
    payer_email: str


class _MerchantsBodyRequired(TypedDict):
    #: Owner email; must be unique across merchants. Example: "owner@shop.example".
    email: str


class MerchantsBody(_MerchantsBodyRequired, total=False):
    """Request body of `POST /v1/merchants`."""

    #: Display name of the merchant. Example: "Acme".
    name: str


class PayIdSelectBody(TypedDict):
    """Request body of `POST /v1/pay/{id}/select`."""

    #: Selected payment currency. Example: "USDT".
    currency: str
    #: Selected network. Example: "tron".
    network: NetworkArg


class _PaymentBodyRequired(TypedDict):
    #: Amount to pay, in currency. Example: "10".
    amount: Money
    #: Price currency code: any of the 23 fiats (USD, EUR, RUB, …) or any coin (USDT, BTC, …). JPY
    #: and KRW have zero decimal places. Example: "USD".
    currency: str


class PaymentBody(_PaymentBodyRequired, total=False):
    """Request body of `POST /v1/payment`."""

    #: Under/overpayment tolerance, 0–5 %. Overrides the merchant setting.
    accuracy_payment_percent: float
    #: Private merchant data, echoed back in webhooks (not visible to the buyer).
    additional_data: str
    #: Allow paying up the remaining amount.
    is_payment_multiple: bool
    #: Revive an expired invoice by order_id instead of creating a new one.
    is_refresh: bool
    #: Invoice lifetime in seconds, 300–43200; default 3600. Values outside the range are clamped
    #: to the nearest bound. Example: 3600.
    lifetime_seconds: int
    #: Settlement network (e.g. tron, ethereum). Optional — see the currency and network selection
    #: modes. Example: "tron".
    network: NetworkArg
    #: Merchant reference; idempotency key. Strongly recommended. Example: "order-1".
    order_id: str
    #: Payer email. If set, a cheque is sent there automatically after payment; it is also the
    #: default recipient for POST /v1/payment/send-email.
    payer_email: str
    #: Deprecated: % of the network markup charged to the payer (0–100); payer-facing markups are
    #: configured via discount.
    subtract: int
    #: Payment page theme: dark | light. Example: "dark".
    theme: str
    #: Settlement currency — the crypto used for payment. Defaults to currency (only if currency is
    #: a coin); with a fiat price set it explicitly or omit it together with network. Example:
    #: "USDT".
    to_currency: str
    #: Per-invoice webhook. Requires a registered endpoint (POST /v1/webhooks): delivery is signed
    #: with its secret.
    url_callback: str
    #: "Back to shop" link on the payment page.
    url_return: str
    #: Redirect after successful payment.
    url_success: str


class PaymentAcceptedListBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/accepted/list`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class PaymentAcceptedSetAcceptedItem(TypedDict):
    """Nested body object of `POST /v1/payment/accepted/set`."""

    #: Asset code. Example: "USDT".
    currency: str
    #: Asset network. Example: "tron".
    network: NetworkArg


class PaymentAcceptedSetBody(TypedDict):
    """Request body of `POST /v1/payment/accepted/set`."""

    #: The full list of currency+network pairs payers may use; an empty list accepts everything in
    #: the catalog.
    accepted: List[PaymentAcceptedSetAcceptedItem]


class _PaymentAccuracySetBodyRequired(TypedDict):
    #: Enable/disable the tolerance. Example: true.
    enabled: bool


class PaymentAccuracySetBody(_PaymentAccuracySetBodyRequired, total=False):
    """Request body of `POST /v1/payment/accuracy/set`."""

    #: Tolerance in percent, 1–5. Required when enabled: true; ignored when enabled: false (reset
    #: to 0). Capped at 5 %. Example: 2.
    accuracy_percent: int


class PaymentAutorefundSetBody(TypedDict):
    """Request body of `POST /v1/payment/autorefund/set`."""

    #: Refund the excess on overpayment (paid_over). Example: true.
    overpay: bool
    #: Refund the funds on an expired underpayment (wrong_amount). Example: true.
    underpay: bool


class _PaymentBatchPaymentsItemRequired(TypedDict):
    #: Amount to pay, in currency. Example: "10".
    amount: Money
    #: Price currency code: any of the 23 fiats (USD, EUR, RUB, …) or any coin (USDT, BTC, …). JPY
    #: and KRW have zero decimal places. Example: "USD".
    currency: str
    #: Merchant reference; idempotency key. Strongly recommended. Example: "order-1".
    order_id: str


class PaymentBatchPaymentsItem(_PaymentBatchPaymentsItemRequired, total=False):
    """Nested body object of `POST /v1/payment/batch`."""

    #: Under/overpayment tolerance, 0–5 %. Overrides the merchant setting.
    accuracy_payment_percent: float
    #: Private merchant data, echoed back in webhooks (not visible to the buyer).
    additional_data: str
    #: Allow paying up the remaining amount.
    is_payment_multiple: bool
    #: Revive an expired invoice by order_id instead of creating a new one.
    is_refresh: bool
    #: Invoice lifetime in seconds, 300–43200; default 3600. Values outside the range are clamped
    #: to the nearest bound. Example: 3600.
    lifetime_seconds: int
    #: Settlement network (e.g. tron, ethereum). Optional — see the currency and network selection
    #: modes. Example: "tron".
    network: NetworkArg
    #: Payer email. If set, a cheque is sent there automatically after payment; it is also the
    #: default recipient for POST /v1/payment/send-email.
    payer_email: str
    #: Deprecated: % of the network markup charged to the payer (0–100); payer-facing markups are
    #: configured via discount.
    subtract: int
    #: Payment page theme: dark | light. Example: "dark".
    theme: str
    #: Settlement currency — the crypto used for payment. Defaults to currency (only if currency is
    #: a coin); with a fiat price set it explicitly or omit it together with network. Example:
    #: "USDT".
    to_currency: str
    #: Per-invoice webhook. Requires a registered endpoint (POST /v1/webhooks): delivery is signed
    #: with its secret.
    url_callback: str
    #: "Back to shop" link on the payment page.
    url_return: str
    #: Redirect after successful payment.
    url_success: str


class _PaymentBatchBodyRequired(TypedDict):
    #: Array of 1 to 5000 items — the same fields as POST /v1/payment; set order_id on every item:
    #: results are matched by it and it protects against duplicates.
    payments: List[PaymentBatchPaymentsItem]


class PaymentBatchBody(_PaymentBatchBodyRequired, total=False):
    """Request body of `POST /v1/payment/batch`."""

    #: What to do when an item fails: continue (default) — process the rest; stop — halt processing
    #: after the first error. Example: "continue".
    on_error: BatchOnErrorArg


class PaymentCancelBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/cancel`."""

    #: Your order reference. Example: "order-1".
    order_id: str
    #: Invoice id in Oblodai. Either uuid or order_id is required; uuid takes priority.
    uuid: str


class PaymentDiscountListBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/discount/list`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class _PaymentDiscountSetBodyRequired(TypedDict):
    #: Percentage, from -99 to 99. Positive is a discount, negative is a markup. Example: 3.
    discount_percent: int


class PaymentDiscountSetBody(_PaymentDiscountSetBodyRequired, total=False):
    """Request body of `POST /v1/payment/discount/set`."""

    #: Currency. Empty = global default for all coins. Example: "USDT".
    currency: str
    #: Network. Empty = any network of this currency. Example: "tron".
    network: NetworkArg


class PaymentFeeConfigSetBody(TypedDict):
    """Request body of `POST /v1/payment/fee-config/set`."""

    #: Share of OUR commission paid by the buyer: 0 — the merchant pays (current behaviour), 100 —
    #: the buyer pays and the invoice is issued with a markup. Applies to invoices created AFTER
    #: the change. Example: 100.
    payer_pays_percent: int


class PaymentHistoryBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/history`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int
    #: Filter by status (an exact value from the status vocabulary); empty returns all. Example:
    #: "paid".
    status: PaymentStatusArg


class PaymentInfoBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/info`."""

    #: Your order reference. Example: "order-1".
    order_id: str
    #: Invoice id in Oblodai. Either uuid or order_id is required; uuid takes priority.
    uuid: str


class _PaymentLinkBodyRequired(TypedDict):
    #: Amount mode: fixed | open | range. Example: "open".
    amount_mode: AmountModeArg
    #: Price currency — fiat (USD, EUR, RUB, …) or a coin; see pricing_currencies from GET
    #: /v1/currencies. Example: "USD".
    currency: str


class PaymentLinkBody(_PaymentLinkBodyRequired, total=False):
    """Request body of `POST /v1/payment/link`."""

    #: Amount — for fixed mode; required in this mode. Example: "25.00".
    amount_fixed: Money
    #: Description on the payment page.
    description: str
    #: Link lifetime in seconds from creation; 0 (default) — the link never expires.
    expires_in_seconds: int
    #: Upper bound — for range; required in this mode. Example: "1000.00".
    max_amount: Money
    #: Lower bound: an optional floor for open, a required minimum for range. Example: "1.00".
    min_amount: Money
    #: Settlement currency (coin) pinned to the link; empty — the buyer chooses the coin. Example:
    #: "USDT".
    pinned_currency: str
    #: Settlement network pinned to the link; empty — the buyer chooses the network. Example:
    #: "tron".
    pinned_network: NetworkArg
    #: Title on the payment page.
    title: str


class _PaymentLinkInfoBodyRequired(TypedDict):
    #: Payment link identifier. Example: "5d3f2a71-9c84-4b0e-8d17-3e6a2c9f1b40".
    link_id: str


class PaymentLinkInfoBody(_PaymentLinkInfoBodyRequired, total=False):
    """Request body of `POST /v1/payment/link/info`."""

    #: Page size for the link's payments, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset within the link's payments. Example: 0.
    offset: int


class PaymentLinkListBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/link/list`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class PaymentLinkToggleBody(TypedDict):
    """Request body of `POST /v1/payment/link/toggle`."""

    #: true — the link accepts payments; false — disabled (the page shows the link as inactive).
    #: Example: false.
    active: bool
    #: Payment link identifier. Example: "5d3f2a71-9c84-4b0e-8d17-3e6a2c9f1b40".
    link_id: str


class PaymentQrBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/qr`."""

    #: Your order reference. Example: "order-1".
    order_id: str
    #: Invoice id in Oblodai. Either uuid or order_id is required; uuid takes priority.
    uuid: str


class PaymentRefundBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/refund`."""

    #: Refund destination address. Defaults to the payment's payer_address; required only for
    #: Bitcoin/UTXO.
    address: str
    #: Partial amount. Defaults to the full amount received. Example: "10".
    amount: Money
    #: Network. Example: "tron".
    network: NetworkArg
    #: Your order reference for the payment. Either uuid or order_id is required. Example:
    #: "order-1".
    order_id: str
    #: Optional refund idempotency key: distinguishes two different refunds with the same (payment,
    #: address, amount); a repeat with the same value is deduplicated. This is not order_id.
    reference: str
    #: Payment id. Either uuid or order_id is required.
    uuid: str


class PaymentResendBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/resend`."""

    #: Your order reference. Example: "order-1".
    order_id: str
    #: Invoice id in Oblodai. Either uuid or order_id is required; uuid takes priority.
    uuid: str


class _PaymentResolveBodyRequired(TypedDict):
    #: accept — accept the partial payment, refund — return it to the payer. Example: "accept".
    action: Literal["accept", "refund"]


class PaymentResolveBody(_PaymentResolveBodyRequired, total=False):
    """Request body of `POST /v1/payment/resolve`."""

    #: refund only: refund address. Defaults to the payment's recorded payer_address; if it is
    #: empty (Bitcoin/UTXO) the address is required, otherwise refund.no_address.
    address: str
    #: refund only: refund network, defaults to the payment network.
    network: NetworkArg
    #: Your payment identifier. Example: "ord-1001".
    order_id: str
    #: refund only: your refund deduplication key.
    reference: str
    #: Payment UUID. Either uuid or order_id is required.
    uuid: str


class PaymentSendEmailBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/send-email`."""

    #: Where to send it. Defaults to the payer_email set on the payment. Example:
    #: "buyer@example.com".
    email: str
    #: Your order reference. Example: "order-1".
    order_id: str
    #: Payment id in Oblodai. Either uuid or order_id is required.
    uuid: str


class PaymentServicesBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/services`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class PaymentTestingWebhookBody(TypedDict, total=False):
    """Request body of `POST /v1/payment/testing-webhook`."""

    #: Status in the body. Default paid. Example: "paid".
    status: PaymentStatusArg
    #: Where to send the test body. If not provided, delivery goes to the project's registered
    #: endpoint; without an endpoint it fails with webhook.no_endpoint. Signed with the project
    #: endpoint's secret, including when url is passed explicitly. Example:
    #: "https://shop.example/hook".
    url: str


class _PayoutBodyRequired(TypedDict):
    #: Recipient address.
    address: str
    #: Payout amount, in currency. Example: "25".
    amount: Money
    #: Currency code (for example USDT). Example: "USDT".
    currency: str
    #: Your payout number; idempotency key. Example: "payout-1".
    order_id: str


class PayoutBody(_PayoutBodyRequired, total=False):
    """Request body of `POST /v1/payout`."""

    #: Fund the payout by converting the balance. USDT → currency only. Example: "USDT".
    from_currency: str
    #: Who pays the network fee: true — amount+fee is debited from the balance and the recipient
    #: receives amount; false — the recipient receives amount-fee; not provided — the project
    #: fee-config.
    is_subtract: bool
    #: Destination tag/memo (TON Jetton). Maximum 120 characters.
    memo: str
    #: Network (tron, ethereum, …). Required for coins with several networks. Example: "tron".
    network: NetworkArg
    #: Origin label: api (default) or manual.
    source: str
    #: Custom webhook URL for this payout (passes the SSRF check). Requires a registered endpoint
    #: (POST /v1/webhooks): delivery is signed with its secret.
    url_callback: str


class PayoutApproveBody(TypedDict):
    """Request body of `POST /v1/payout/approve`."""

    #: Payout id.
    uuid: str


class _PayoutBatchPayoutsItemRequired(TypedDict):
    #: Recipient address.
    address: str
    #: Payout amount, in currency. Example: "25".
    amount: Money
    #: Currency code (for example USDT). Example: "USDT".
    currency: str
    #: Your payout number; idempotency key. Example: "payout-1".
    order_id: str


class PayoutBatchPayoutsItem(_PayoutBatchPayoutsItemRequired, total=False):
    """Nested body object of `POST /v1/payout/batch`."""

    #: Fund the payout by converting the balance. USDT → currency only. Example: "USDT".
    from_currency: str
    #: Who pays the network fee: true — amount+fee is debited from the balance and the recipient
    #: receives amount; false — the recipient receives amount-fee; not provided — the project
    #: fee-config.
    is_subtract: bool
    #: Destination tag/memo (TON Jetton). Maximum 120 characters.
    memo: str
    #: Network (tron, ethereum, …). Required for coins with several networks. Example: "tron".
    network: NetworkArg
    #: Origin label: api (default) or manual.
    source: str
    #: Custom webhook URL for this payout (passes the SSRF check). Requires a registered endpoint
    #: (POST /v1/webhooks): delivery is signed with its secret.
    url_callback: str


class _PayoutBatchBodyRequired(TypedDict):
    #: Array of 1 to 5000 items — the same fields as POST /v1/payout; order_id is required on every
    #: item and serves as the idempotency key: a repeat returns the already created payout.
    payouts: List[PayoutBatchPayoutsItem]


class PayoutBatchBody(_PayoutBatchBodyRequired, total=False):
    """Request body of `POST /v1/payout/batch`."""

    #: What to do when an item fails: continue (default) — process the rest; stop — halt processing
    #: after the first error. Example: "continue".
    on_error: BatchOnErrorArg


class _PayoutCalculateBodyRequired(TypedDict):
    #: Payout amount as a decimal string. Example: "10".
    amount: Money
    #: Payout asset (USDT, BTC, …). Example: "USDT".
    currency: str


class PayoutCalculateBody(_PayoutCalculateBodyRequired, total=False):
    """Request body of `POST /v1/payout/calculate`."""

    #: true — the fee is debited from the balance on top of the amount (the recipient gets exactly
    #: amount); false — the fee is taken out of the payout.
    is_subtract: bool
    #: Payout network; required when the asset lives on several networks. Example: "tron".
    network: NetworkArg


class PayoutCancelBody(TypedDict):
    """Request body of `POST /v1/payout/cancel`."""

    #: Id of the payout (or refund) to cancel.
    uuid: str


class PayoutFeeConfigSetBody(TypedDict):
    """Request body of `POST /v1/payout/fee-config/set`."""

    #: true — the recipient pays the network fee (receives less); false — the merchant bears the
    #: fee. Example: true.
    fee_on_recipient: bool


class PayoutHistoryBody(TypedDict, total=False):
    """Request body of `POST /v1/payout/history`."""

    #: payout — ordinary payouts, refund — refunds; empty returns both. Example: "payout".
    kind: Literal["payout", "refund"]
    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int
    #: Filter by status (an exact value from the status vocabulary); empty returns all. Example:
    #: "paid".
    status: PayoutStatusArg


class PayoutInfoBody(TypedDict, total=False):
    """Request body of `POST /v1/payout/info`."""

    #: Your order reference. Example: "order-1".
    order_id: str
    #: Invoice id in Oblodai. Either uuid or order_id is required; uuid takes priority.
    uuid: str


class _PayoutLinkBodyRequired(TypedDict):
    #: Amount in currency, as a string; greater than zero. Example: "25".
    amount: Money
    #: Payout crypto asset (USDT, BTC, …); fiat is not possible. Example: "USDT".
    currency: str
    #: Payout network for the recipient (tron, bitcoin, …). Example: "tron".
    network: NetworkArg


class PayoutLinkBody(_PayoutLinkBodyRequired, total=False):
    """Request body of `POST /v1/payout/link`."""

    #: If set, the recipient receives an email with a "Claim funds" button; a delivery failure does
    #: not cancel link creation. Example: "user@example.com".
    email: str
    #: Link lifetime in seconds, clamped to 3600–2592000 (one hour to 30 days); without the field
    #: or with 0 the link lives 1 hour, not the maximum — set it explicitly. Example: 604800.
    expires_in_seconds: int
    #: Who pays the network fee: "recipient" (default — deducted from the amount, the recipient
    #: receives less) or "merchant" (the amount plus the fee is reserved, the recipient receives
    #: exactly amount). Example: "merchant".
    fee_bearer: FeeBearerArg
    #: Message to the recipient (shown on the claim page and in the email).
    note: str
    #: Claim code — a second factor for the link: "auto" — we generate it and return it ONCE in the
    #: response, or your own (6–64 visible characters), empty — no code. Pass the code to the
    #: recipient over a channel SEPARATE from the link (it is not put into the email); after 10
    #: incorrect attempts the link is locked. Example: "auto".
    passcode: str
    #: Your deduplication key, unique per merchant; the Idempotency-Key header has no effect on
    #: this endpoint. Example: "bonus-42".
    reference: str
    #: Title — shown to the recipient on the claim page.
    title: str


class _PayoutLinkBatchItemsItemRequired(TypedDict):
    #: Amount in currency, as a string; greater than zero. Example: "25".
    amount: Money
    #: Payout crypto asset (USDT, BTC, …); fiat is not possible. Example: "USDT".
    currency: str
    #: Payout network for the recipient (tron, bitcoin, …). Example: "tron".
    network: NetworkArg
    #: Your deduplication key, unique per merchant; the Idempotency-Key header has no effect on
    #: this endpoint. Example: "bonus-42".
    reference: str


class PayoutLinkBatchItemsItem(_PayoutLinkBatchItemsItemRequired, total=False):
    """Nested body object of `POST /v1/payout/link/batch`."""

    #: If set, the recipient receives an email with a "Claim funds" button; a delivery failure does
    #: not cancel link creation. Example: "user@example.com".
    email: str
    #: Link lifetime in seconds, clamped to 3600–2592000 (one hour to 30 days); without the field
    #: or with 0 the link lives 1 hour, not the maximum — set it explicitly. Example: 604800.
    expires_in_seconds: int
    #: Who pays the network fee: "recipient" (default — deducted from the amount, the recipient
    #: receives less) or "merchant" (the amount plus the fee is reserved, the recipient receives
    #: exactly amount). Example: "merchant".
    fee_bearer: FeeBearerArg
    #: Message to the recipient (shown on the claim page and in the email).
    note: str
    #: Claim code — a second factor for the link: "auto" — we generate it and return it ONCE in the
    #: response, or your own (6–64 visible characters), empty — no code. Pass the code to the
    #: recipient over a channel SEPARATE from the link (it is not put into the email); after 10
    #: incorrect attempts the link is locked. Example: "auto".
    passcode: str
    #: Title — shown to the recipient on the claim page.
    title: str


class PayoutLinkBatchBody(TypedDict):
    """Request body of `POST /v1/payout/link/batch`."""

    #: Up to 500 links per call; each one succeeds or fails independently, the response is aligned
    #: with the request indexes.
    items: List[PayoutLinkBatchItemsItem]


class PayoutLinkCancelBody(TypedDict):
    """Request body of `POST /v1/payout/link/cancel`."""

    #: Payout link id (link_id from the creation response).
    link_id: str


class _PayoutLinkChequeBodyRequired(TypedDict):
    #: Claim secret from the payout link creation response. Stored only as a hash and never
    #: reissued — the cheque can be printed only while you still hold the token.
    claim_token: str


class PayoutLinkChequeBody(_PayoutLinkChequeBodyRequired, total=False):
    """Request body of `POST /v1/payout/link/cheque`."""

    #: Document language — one of the 41 supported codes (en by default); the full list is in the
    #: document.unknown_lang error. Example: "ru".
    lang: str


class PayoutLinkInfoBody(TypedDict):
    """Request body of `POST /v1/payout/link/info`."""

    #: Payout link id (link_id from the creation response).
    link_id: str


class PayoutLinkListBody(TypedDict, total=False):
    """Request body of `POST /v1/payout/link/list`."""

    #: How many links to return per page. Example: 50.
    limit: int
    #: Offset from the start of the list (paging). Example: 0.
    offset: int


class _PayoutMassPayoutsItemRequired(TypedDict):
    #: Recipient address.
    address: str
    #: Payout amount, in currency. Example: "25".
    amount: Money
    #: Currency code (for example USDT). Example: "USDT".
    currency: str
    #: Your payout number; idempotency key. Example: "payout-1".
    order_id: str


class PayoutMassPayoutsItem(_PayoutMassPayoutsItemRequired, total=False):
    """Nested body object of `POST /v1/payout/mass`."""

    #: Fund the payout by converting the balance. USDT → currency only. Example: "USDT".
    from_currency: str
    #: Who pays the network fee: true — amount+fee is debited from the balance and the recipient
    #: receives amount; false — the recipient receives amount-fee; not provided — the project
    #: fee-config.
    is_subtract: bool
    #: Destination tag/memo (TON Jetton). Maximum 120 characters.
    memo: str
    #: Network (tron, ethereum, …). Required for coins with several networks. Example: "tron".
    network: NetworkArg
    #: Origin label: api (default) or manual.
    source: str
    #: Custom webhook URL for this payout (passes the SSRF check). Requires a registered endpoint
    #: (POST /v1/webhooks): delivery is signed with its secret.
    url_callback: str


class _PayoutMassBodyRequired(TypedDict):
    #: Array of up to 100 items; the fields of each are as in POST /v1/payout.
    payouts: List[PayoutMassPayoutsItem]


class PayoutMassBody(_PayoutMassBodyRequired, total=False):
    """Request body of `POST /v1/payout/mass`."""

    #: Origin label, applied to every item without its own source.
    source: str


class PayoutRefundFeeConfigSetBody(TypedDict):
    """Request body of `POST /v1/payout/refund-fee-config/set`."""

    #: true — the customer receives net (the customer pays the fee); false — the merchant pays the
    #: fee and the customer receives gross. Example: true.
    fee_on_customer: bool


class PayoutServicesBody(TypedDict, total=False):
    """Request body of `POST /v1/payout/services`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class _PayoutValidateBodyRequired(TypedDict):
    #: Recipient address.
    address: str
    #: Payout amount, in currency. Example: "25".
    amount: Money
    #: Currency code (for example USDT). Example: "USDT".
    currency: str


class PayoutValidateBody(_PayoutValidateBodyRequired, total=False):
    """Request body of `POST /v1/payout/validate`."""

    #: Fund the payout by converting the balance. USDT → currency only. Example: "USDT".
    from_currency: str
    #: Who pays the network fee: true — amount+fee is debited from the balance and the recipient
    #: receives amount; false — the recipient receives amount-fee; not provided — the project
    #: fee-config.
    is_subtract: bool
    #: Destination tag/memo (TON Jetton). Maximum 120 characters.
    memo: str
    #: Network (tron, ethereum, …). Required for coins with several networks. Example: "tron".
    network: NetworkArg
    #: Your payout number; idempotency key. Example: "payout-1".
    order_id: str
    #: Origin label: api (default) or manual.
    source: str
    #: Custom webhook URL for this payout (passes the SSRF check). Requires a registered endpoint
    #: (POST /v1/webhooks): delivery is signed with its secret.
    url_callback: str


class _RefundBatchRefundsItemRequired(TypedDict):
    #: Optional refund idempotency key: distinguishes two different refunds with the same (payment,
    #: address, amount); a repeat with the same value is deduplicated. This is not order_id.
    reference: str


class RefundBatchRefundsItem(_RefundBatchRefundsItemRequired, total=False):
    """Nested body object of `POST /v1/refund/batch`."""

    #: Refund destination address. Defaults to the payment's payer_address; required only for
    #: Bitcoin/UTXO.
    address: str
    #: Partial amount. Defaults to the full amount received. Example: "10".
    amount: Money
    #: Network. Example: "tron".
    network: NetworkArg
    #: Your order reference for the payment. Either uuid or order_id is required. Example:
    #: "order-1".
    order_id: str
    #: Payment id. Either uuid or order_id is required.
    uuid: str


class _RefundBatchBodyRequired(TypedDict):
    #: Array of 1 to 5000 items — the same fields as POST /v1/payment/refund; every item requires
    #: reference (idempotency key) and either uuid or order_id of the payment.
    refunds: List[RefundBatchRefundsItem]


class RefundBatchBody(_RefundBatchBodyRequired, total=False):
    """Request body of `POST /v1/refund/batch`."""

    #: What to do when an item fails: continue (default) — process the rest; stop — halt processing
    #: after the first error. Example: "continue".
    on_error: BatchOnErrorArg


class _SandboxDepositBodyRequired(TypedDict):
    #: UUID of the test invoice being "paid".
    invoice_id: str


class SandboxDepositBody(_SandboxDepositBodyRequired, total=False):
    """Request body of `POST /v1/sandbox/deposit`."""

    #: Amount in the invoice currency; empty — pay exactly what is due, anything else is a way to
    #: produce an under/overpayment. Example: "10".
    amount: Money
    #: How many confirmations the deposit arrived with; 0 — fully confirmed; fewer than required —
    #: a way to test the pending→confirmed transition (repeat the same txid with a higher number).
    #: Example: 0.
    confirmations: int
    #: Repeating the same txid tests your idempotency; empty — a new txid.
    txid: str


class _SandboxFaucetBodyRequired(TypedDict):
    #: Amount of test money, as a string; capped at 1000000 per call. Example: "1000".
    amount: Money
    #: Top-up asset (USDT, BTC, …). Example: "USDT".
    asset: str


class SandboxFaucetBody(_SandboxFaucetBodyRequired, total=False):
    """Request body of `POST /v1/sandbox/faucet`."""

    #: Safe-retry key; empty — every call creates a new top-up.
    idempotency_key: str


class SandboxWebhooksReplayBody(TypedDict):
    """Request body of `POST /v1/sandbox/webhooks/replay`."""

    #: Delivery id from GET /v1/sandbox/webhooks.
    delivery_id: str


class SplitConfigSetBody(TypedDict):
    """Request body of `POST /v1/split/config/set`."""

    #: How many seconds to defer split settlement; range 0–7776000 (up to 90 days). 0 — send the
    #: shares immediately: you take on the risk that a refund becomes impossible. Example: 172800.
    refund_hold_seconds: int


class SplitRecipientOptinBody(TypedDict):
    """Request body of `POST /v1/split/recipient/optin`."""

    #: Allow other merchants to route split shares to your balance. true — enable receiving, false
    #: — disable (new rules targeting you stop being created; existing ones keep executing).
    #: Example: true.
    enabled: bool


class _SplitRuleBodyRequired(TypedDict):
    #: Share of every payment, as a string: "10" = 10 %, "2.5" = 2.5 %. Greater than 0 and at most
    #: 100, step 0.01 %; the sum of all rules cannot exceed 100 %. Example: "10".
    percent: str


class SplitRuleBody(_SplitRuleBodyRequired, total=False):
    """Request body of `POST /v1/split/rule`."""

    #: External crypto address of the partner; the share leaves as a real on-chain transaction —
    #: irreversible. Exactly one recipient option: either address+network or merchant_id.
    address: str
    #: Id of the partner merchant inside Oblodai; the share moves through internal accounting and
    #: is clawed back on a refund. Example: "b4c1f0e2-5a77-4d31-9f08-2c6e7a1b3d94".
    merchant_id: str
    #: Address network. Required together with address. Example: "tron".
    network: NetworkArg
    #: Comment for yourself (shown in the rule list).
    note: str


class SplitRuleDeleteBody(TypedDict):
    """Request body of `POST /v1/split/rule/delete`."""

    #: Rule identifier from POST /v1/split/rule or the list. Example:
    #: "9f4c1a2b-77de-4a55-9c1f-0e2b3d4a5f60".
    rule_id: str


class SplitRuleListBody(TypedDict, total=False):
    """Request body of `POST /v1/split/rule/list`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


class _TestWebhookPaymentBodyRequired(TypedDict):
    #: Where to send the test body. Example: "https://shop.example/oblodai/callback".
    url_callback: str


class TestWebhookPaymentBody(_TestWebhookPaymentBodyRequired, total=False):
    """Request body of `POST /v1/test-webhook/payment`."""

    #: Currency in the body. Example: "USDT".
    currency: str
    #: Network in the body. Example: "tron".
    network: NetworkArg
    #: Your order_id, which is put into the test event body.
    order_id: str
    #: Status in the body — from the status dictionary of this event type. Default paid (confirmed
    #: for a payout). Example: "paid".
    status: PaymentStatusArg
    #: UUID of the object (payment, wallet or payout) put into the test event body.
    uuid: str


class _TestWebhookPayoutBodyRequired(TypedDict):
    #: Where to send the test body. Example: "https://shop.example/oblodai/callback".
    url_callback: str


class TestWebhookPayoutBody(_TestWebhookPayoutBodyRequired, total=False):
    """Request body of `POST /v1/test-webhook/payout`."""

    #: Currency in the body. Example: "USDT".
    currency: str
    #: Network in the body. Example: "tron".
    network: NetworkArg
    #: Your order_id, which is put into the test event body.
    order_id: str
    #: Status in the body — from the status dictionary of this event type. Default paid (confirmed
    #: for a payout). Example: "paid".
    status: PayoutStatusArg
    #: UUID of the object (payment, wallet or payout) put into the test event body.
    uuid: str


class _TestWebhookWalletBodyRequired(TypedDict):
    #: Where to send the test body. Example: "https://shop.example/oblodai/callback".
    url_callback: str


class TestWebhookWalletBody(_TestWebhookWalletBodyRequired, total=False):
    """Request body of `POST /v1/test-webhook/wallet`."""

    #: Currency in the body. Example: "USDT".
    currency: str
    #: Network in the body. Example: "tron".
    network: NetworkArg
    #: Your order_id, which is put into the test event body.
    order_id: str
    #: Status in the body — from the status dictionary of this event type. Default paid (confirmed
    #: for a payout). Example: "paid".
    status: Literal["paid"]
    #: UUID of the object (payment, wallet or payout) put into the test event body.
    uuid: str


class TransferBatchTransfersItem(TypedDict):
    """Nested body object of `POST /v1/transfer/batch`."""

    #: Transfer amount in currency. Example: "50".
    amount: Money
    #: Currency code (cryptocurrency). Example: "USDT".
    currency: str
    #: Idempotency key: a repeat with the same order_id is a no-op; required in a transfer batch.
    order_id: str
    #: Platform user id of the recipient (UUID, not username); a username is resolved to an id via
    #: the cabinet public profile /public/users/{username}.
    to_user_id: str


class TransferBatchBody(TypedDict, total=False):
    """Request body of `POST /v1/transfer/batch`."""

    #: What to do when an item fails: continue (default) — process the rest; stop — halt processing
    #: after the first error. Example: "continue".
    on_error: BatchOnErrorArg
    #: Array of 1 to 5000 items — the same fields as POST /v1/transfer/to-user; every item requires
    #: order_id (idempotency key) and to_user_id (user UUID).
    transfers: List[TransferBatchTransfersItem]


class _TransferToPersonalBodyRequired(TypedDict):
    #: Transfer amount in currency. Example: "50".
    amount: Money
    #: Currency code (cryptocurrency). Example: "USDT".
    currency: str


class TransferToPersonalBody(_TransferToPersonalBodyRequired, total=False):
    """Request body of `POST /v1/transfer/to-personal`."""

    #: Idempotency key: a repeat with the same order_id is a no-op. Always send it, otherwise
    #: retrying the request after a network timeout creates a second transfer. Example:
    #: "transfer-1".
    order_id: str


class _TransferToUserBodyRequired(TypedDict):
    #: Transfer amount in currency. Example: "50".
    amount: Money
    #: Currency code (cryptocurrency). Example: "USDT".
    currency: str
    #: Platform user id of the recipient (UUID, not username); a username is resolved to an id via
    #: the cabinet public profile /public/users/{username}.
    to_user_id: str


class TransferToUserBody(_TransferToUserBodyRequired, total=False):
    """Request body of `POST /v1/transfer/to-user`."""

    #: Idempotency key: a repeat with the same order_id is a no-op; required in a transfer batch.
    order_id: str


class VrcsBody(TypedDict, total=False):
    """Request body of `POST /v1/vrcs`."""

    #: true — enable auto-conversion of volatile deposits to USDT, false — disable; omit to read
    #: the current state. Example: true.
    enabled: bool


class _WalletBodyRequired(TypedDict):
    #: Symbol of the receiving currency (USDT, BTC, ETH, …). Example: "USDT".
    currency: str
    #: Receiving network (tron, ethereum, bitcoin, …). Example: "tron".
    network: NetworkArg


class WalletBody(_WalletBodyRequired, total=False):
    """Request body of `POST /v1/wallet`."""

    #: Your customer/order identifier. Pins a dedicated permanent address to the customer. Example:
    #: "client-42".
    order_id: str


class _WalletBlockBodyRequired(TypedDict):
    #: Static wallet address. Example: "TXk9...c3Fd".
    address: str


class WalletBlockBody(_WalletBlockBodyRequired, total=False):
    """Request body of `POST /v1/wallet/block`."""

    #: true — block (the default when the field is omitted); false — unblock.
    is_force_block: bool


class _WalletBlockedAddressRefundBodyRequired(TypedDict):
    #: Refund destination address.
    address: str
    #: Static wallet id (from the /v1/wallet response).
    uuid: str


class WalletBlockedAddressRefundBody(_WalletBlockedAddressRefundBodyRequired, total=False):
    """Request body of `POST /v1/wallet/blocked-address-refund`."""

    #: Destination tag/memo (XRP destination tag, XLM memo id, TON comment). Required for a classic
    #: address on a tag/memo network if the tag is not embedded in the X-/M-address.
    memo: str


class WalletQrBody(TypedDict):
    """Request body of `POST /v1/wallet/qr`."""

    #: Arbitrary address to render into a QR code (PNG as a data: URI).
    address: str


class WebhooksBody(TypedDict):
    """Request body of `POST /v1/webhooks`."""

    #: HTTPS callback URL. SSRF check: private and local addresses are rejected. Example:
    #: "https://shop.example/oblodai/callback".
    url: str


class WebhooksDeliveriesBody(TypedDict, total=False):
    """Request body of `POST /v1/webhooks/deliveries`."""

    #: Page size, 1–100; out of range falls back to 25. Example: 25.
    limit: int
    #: Offset from the start of the list (newest first). Example: 0.
    offset: int


#: Route key -> the TypedDict describing its request body.

REQUEST_BODIES: Mapping[str, str] = {
    "POST /v1/api-allowlist/add": "ApiAllowlistAddBody",
    "POST /v1/api-allowlist/enable": "ApiAllowlistEnableBody",
    "POST /v1/api-allowlist/remove": "ApiAllowlistRemoveBody",
    "POST /v1/auto-withdraw/delete": "AutoWithdrawDeleteBody",
    "POST /v1/auto-withdraw/set": "AutoWithdrawSetBody",
    "POST /v1/batch/info": "BatchInfoBody",
    "POST /v1/claim/{token}": "ClaimTokenBody",
    "POST /v1/documents/jobs": "DocumentsJobsBody",
    "POST /v1/documents/jobs/info": "DocumentsJobsInfoBody",
    "POST /v1/exchange-rate/list": "ExchangeRateListBody",
    "POST /v1/link/{id}/checkout": "LinkIdCheckoutBody",
    "POST /v1/merchants": "MerchantsBody",
    "POST /v1/pay/{id}/select": "PayIdSelectBody",
    "POST /v1/payment": "PaymentBody",
    "POST /v1/payment/accepted/list": "PaymentAcceptedListBody",
    "POST /v1/payment/accepted/set": "PaymentAcceptedSetBody",
    "POST /v1/payment/accuracy/set": "PaymentAccuracySetBody",
    "POST /v1/payment/autorefund/set": "PaymentAutorefundSetBody",
    "POST /v1/payment/batch": "PaymentBatchBody",
    "POST /v1/payment/cancel": "PaymentCancelBody",
    "POST /v1/payment/discount/list": "PaymentDiscountListBody",
    "POST /v1/payment/discount/set": "PaymentDiscountSetBody",
    "POST /v1/payment/fee-config/set": "PaymentFeeConfigSetBody",
    "POST /v1/payment/history": "PaymentHistoryBody",
    "POST /v1/payment/info": "PaymentInfoBody",
    "POST /v1/payment/link": "PaymentLinkBody",
    "POST /v1/payment/link/info": "PaymentLinkInfoBody",
    "POST /v1/payment/link/list": "PaymentLinkListBody",
    "POST /v1/payment/link/toggle": "PaymentLinkToggleBody",
    "POST /v1/payment/qr": "PaymentQrBody",
    "POST /v1/payment/refund": "PaymentRefundBody",
    "POST /v1/payment/resend": "PaymentResendBody",
    "POST /v1/payment/resolve": "PaymentResolveBody",
    "POST /v1/payment/send-email": "PaymentSendEmailBody",
    "POST /v1/payment/services": "PaymentServicesBody",
    "POST /v1/payment/testing-webhook": "PaymentTestingWebhookBody",
    "POST /v1/payout": "PayoutBody",
    "POST /v1/payout/approve": "PayoutApproveBody",
    "POST /v1/payout/batch": "PayoutBatchBody",
    "POST /v1/payout/calculate": "PayoutCalculateBody",
    "POST /v1/payout/cancel": "PayoutCancelBody",
    "POST /v1/payout/fee-config/set": "PayoutFeeConfigSetBody",
    "POST /v1/payout/history": "PayoutHistoryBody",
    "POST /v1/payout/info": "PayoutInfoBody",
    "POST /v1/payout/link": "PayoutLinkBody",
    "POST /v1/payout/link/batch": "PayoutLinkBatchBody",
    "POST /v1/payout/link/cancel": "PayoutLinkCancelBody",
    "POST /v1/payout/link/cheque": "PayoutLinkChequeBody",
    "POST /v1/payout/link/info": "PayoutLinkInfoBody",
    "POST /v1/payout/link/list": "PayoutLinkListBody",
    "POST /v1/payout/mass": "PayoutMassBody",
    "POST /v1/payout/refund-fee-config/set": "PayoutRefundFeeConfigSetBody",
    "POST /v1/payout/services": "PayoutServicesBody",
    "POST /v1/payout/validate": "PayoutValidateBody",
    "POST /v1/refund/batch": "RefundBatchBody",
    "POST /v1/sandbox/deposit": "SandboxDepositBody",
    "POST /v1/sandbox/faucet": "SandboxFaucetBody",
    "POST /v1/sandbox/webhooks/replay": "SandboxWebhooksReplayBody",
    "POST /v1/split/config/set": "SplitConfigSetBody",
    "POST /v1/split/recipient/optin": "SplitRecipientOptinBody",
    "POST /v1/split/rule": "SplitRuleBody",
    "POST /v1/split/rule/delete": "SplitRuleDeleteBody",
    "POST /v1/split/rule/list": "SplitRuleListBody",
    "POST /v1/test-webhook/payment": "TestWebhookPaymentBody",
    "POST /v1/test-webhook/payout": "TestWebhookPayoutBody",
    "POST /v1/test-webhook/wallet": "TestWebhookWalletBody",
    "POST /v1/transfer/batch": "TransferBatchBody",
    "POST /v1/transfer/to-personal": "TransferToPersonalBody",
    "POST /v1/transfer/to-user": "TransferToUserBody",
    "POST /v1/vrcs": "VrcsBody",
    "POST /v1/wallet": "WalletBody",
    "POST /v1/wallet/block": "WalletBlockBody",
    "POST /v1/wallet/blocked-address-refund": "WalletBlockedAddressRefundBody",
    "POST /v1/wallet/qr": "WalletQrBody",
    "POST /v1/webhooks": "WebhooksBody",
    "POST /v1/webhooks/deliveries": "WebhooksDeliveriesBody",
}
