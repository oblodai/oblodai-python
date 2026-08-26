"""Invoices, QR codes, underpayment resolutions, service catalogues and batch acknowledgements."""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple, TypedDict, Union

from ..enums import PaymentStatus, PayoutStatus
from .common import Money, Timestamp
from .payouts import _PayoutRequired


class PaymentTx(TypedDict):
    """One on-chain deposit attributed to an invoice (an element of `tx_list`)."""

    #: Transaction hash.
    txid: str
    #: Transfer amount in the payment currency.
    amount: Money
    #: Network the transfer arrived on. On EVM it may differ from the invoice network: a
    #: deposit is credited on another chain with the same address too. Vocabulary: `Network`.
    network: str
    #: Height of the block the transfer was confirmed in.
    height: int
    #: When the transfer was credited (ISO 8601).
    created_at: Timestamp


class PaymentRefund(TypedDict):
    """A refund issued against an invoice (a payout in disguise; full detail via `payouts.info`)."""

    uuid: str
    address: str
    amount: Money
    status: PayoutStatus
    is_final: bool
    txid: str
    created_at: Timestamp


class _PaymentRequired(TypedDict):
    #: Our payment id (use it in info/refund).
    uuid: str
    #: Your order number, passed at creation.
    order_id: str
    #: Status: select (the customer is choosing a currency) | created (waiting for payment) |
    #: confirm_check (payment seen, waiting for confirmations; with amount_remaining > 0 it is
    #: partial and the remainder is awaited) | paid | paid_over (overpayment) | wrong_amount
    #: (underpayment, deadline passed) | expired | cancelled.
    status: PaymentStatus
    #: true — the status is final and will not change again.
    is_final: bool
    #: Amount due in the price currency (for example, in USD).
    amount: Money
    #: Price currency: fiat (USD, EUR, RUB, JPY… — see pricing_currencies) or a coin. Tells what
    #: the invoice COSTS, not what it is paid with (that is payer_currency).
    currency: str
    #: Blockchain network (for example, tron). Empty until the payer selects one on a
    #: multi-network invoice. Vocabulary: `Network`.
    network: str
    #: How much must be sent in the payment crypto.
    payer_amount: Money
    #: Currency the customer pays in (for example, USDT). Empty for a currency-agnostic invoice
    #: (is_multi) until the customer picks a coin — it has no settlement currency yet.
    payer_currency: str
    #: How much has already been confirmed as paid, in the payment crypto; always a string (0 if
    #: nothing arrived).
    amount_paid: Money
    #: How much is still left to pay (due − paid); 0 if enough has arrived.
    amount_remaining: Money
    #: Address the customer sends the funds to. On XRP this is the classic r-address of the
    #: SHARED wallet — the payment must carry destination_tag, otherwise the network rejects it.
    address: str
    #: XRP only: numeric destination tag the customer MUST include in the transfer (the "tag/memo
    #: of the recipient" field on an exchange or in a wallet). Empty on other networks.
    destination_tag: str
    #: XLM (Stellar) only: numeric memo (type ID) the customer MUST include in the transfer — the
    #: "memo" field on an exchange or in a wallet. Empty on other networks.
    memo: str
    #: XRP only: the same details in one string in X-address format (XLS-5) — address and tag
    #: together; the QR encodes it as well. Empty on other networks.
    address_xaddress: str
    #: XLM only: the same details in one string — muxed address M… (SEP-23), address and memo
    #: together; the QR encodes it as well. Empty on other networks.
    address_muxed: str
    #: Address QR code as a PNG data: URI — can be used directly in <img src>. On XRP it encodes
    #: the X-address (address+tag in one string).
    address_qr_code: str
    #: true — this is a currency-agnostic link, the customer has not chosen a currency/network yet.
    is_multi: bool
    #: Link to the hosted payment page.
    url: str
    #: "Back to shop" link shown before payment.
    url_return: str
    #: Where to redirect after successful payment.
    url_success: str
    #: When the invoice expires (ISO 8601, like all time fields).
    expired_at: Timestamp
    #: When the rate will be refreshed (ISO 8601; the rate holds for ~5 min).
    rate_expires_at: Timestamp
    #: Rate locked by this invoice (how much payment currency per 1 unit of the price currency) —
    #: payer_amount is calculated from it. Empty until the currency is chosen.
    exchange_rate: Money
    #: Current number of confirmations of the incoming payment.
    confirmations: int
    #: How many confirmations are needed for crediting (depends on the amount and the network).
    required_confirmations: int
    #: Hash of the incoming transaction (once it is seen).
    txid: str
    #: All confirmed transfers that paid the invoice. Partial payment in several transfers is the
    #: regular wrong_amount scenario; the single txid at the top level is only the last one seen.
    tx_list: List[PaymentTx]
    #: Moment of the actual payment — crediting of the last confirmed transfer (ISO 8601). null
    #: until the payment arrives. Distinguish it from updated_at, which shifts on any change.
    paid_at: Optional[Timestamp]
    #: Address the first confirmed deposit came FROM — on account-based networks
    #: (EVM/Tron/Solana/TON); empty on UTXO. ⚠ This is NOT necessarily a refund address: the
    #: sender may be an exchange, the change of a UTXO transaction or the hot omnibus of a crypto
    #: on-ramp if the buyer paid by card. Check payer_address_is_refundable before refunding here.
    payer_address: str
    #: true — payer_address belongs to the payer and address may be omitted in /v1/payment/refund
    #: (we refund to it). false — the refund address is unknown (UTXO/XRP, card payment via an
    #: on-ramp, address not recorded): ask the buyer for an address and pass address explicitly,
    #: otherwise the request is rejected with refund.no_address.
    payer_address_is_refundable: bool
    #: Payer e-mail, if you passed one.
    payer_email: str
    #: Your private data, returned in the response and in the webhook.
    additional_data: str
    #: Our commission on this payment, in the payment currency. The invoice rate already includes
    #: the amortized fixed fee — it is not charged a second time. Empty for a currency-agnostic
    #: invoice until a coin is chosen; 0 while nothing has been credited.
    commission: Money
    #: How much is (or will be) credited to you: amount_paid − commission. The network costs of
    #: collecting the deposit are borne by the gateway — they are NOT deducted from this amount.
    merchant_amount: Money
    #: Signed link to the PDF cheque for this operation — opens without an API key, can be
    #: attached to an email or handed to the customer. Empty if document generation is disabled.
    document_url: str
    #: true — a sandbox invoice (dev shop): the money is not real, do not include it in live
    #: reconciliation.
    is_test: bool
    #: Creation time (ISO 8601).
    created_at: Timestamp
    #: Time of the last change (ISO 8601).
    updated_at: Timestamp


class Payment(_PaymentRequired, total=False):
    """Invoice as `/v1/payment`, `/v1/payment/info`, `/v1/payment/history` and
    `/v1/payment/cancel` render it (core `paymentResult`). `refunds`/`refund_status` are present
    on `info` only."""

    #: Refunds issued against this invoice (`info` only).
    refunds: List[PaymentRefund]
    #: Aggregate refund state of the invoice (`info` only).
    refund_status: str


PAYMENT_KEYS: Tuple[str, ...] = (
    "uuid",
    "order_id",
    "status",
    "is_final",
    "amount",
    "currency",
    "network",
    "payer_amount",
    "payer_currency",
    "amount_paid",
    "amount_remaining",
    "address",
    "destination_tag",
    "memo",
    "address_xaddress",
    "address_muxed",
    "address_qr_code",
    "is_multi",
    "url",
    "url_return",
    "url_success",
    "expired_at",
    "rate_expires_at",
    "exchange_rate",
    "confirmations",
    "required_confirmations",
    "txid",
    "tx_list",
    "paid_at",
    "payer_address",
    "payer_address_is_refundable",
    "payer_email",
    "additional_data",
    "commission",
    "merchant_amount",
    "document_url",
    "is_test",
    "created_at",
    "updated_at",
)


class PublicPayment(TypedDict):
    """The payer-facing view (`GET /v1/pay/{id}`, `/select`, link checkout): no
    merchant-only fields (no commission, merchant_amount, payer_email, additional_data,
    tx_list, paid_at, is_test or document_url)."""

    #: Our payment id (use it in info/refund).
    uuid: str
    #: Your order number, passed at creation.
    order_id: str
    #: Status: select (the customer is choosing a currency) | created (waiting for payment) |
    #: confirm_check (payment seen, waiting for confirmations; with amount_remaining > 0 it is
    #: partial and the remainder is awaited) | paid | paid_over (overpayment) | wrong_amount
    #: (underpayment, deadline passed) | expired | cancelled.
    status: PaymentStatus
    #: true — the status is final and will not change again.
    is_final: bool
    #: Amount due in the price currency (for example, in USD).
    amount: Money
    #: Price currency: fiat (USD, EUR, RUB, JPY… — see pricing_currencies) or a coin. Tells what
    #: the invoice COSTS, not what it is paid with (that is payer_currency).
    currency: str
    #: Blockchain network (for example, tron). Empty until the payer selects one on a
    #: multi-network invoice. Vocabulary: `Network`.
    network: str
    #: How much must be sent in the payment crypto.
    payer_amount: Money
    #: Currency the customer pays in (for example, USDT). Empty for a currency-agnostic invoice
    #: (is_multi) until the customer picks a coin — it has no settlement currency yet.
    payer_currency: str
    #: How much has already been confirmed as paid, in the payment crypto; always a string (0 if
    #: nothing arrived).
    amount_paid: Money
    #: How much is still left to pay (due − paid); 0 if enough has arrived.
    amount_remaining: Money
    #: Address the customer sends the funds to. On XRP this is the classic r-address of the
    #: SHARED wallet — the payment must carry destination_tag, otherwise the network rejects it.
    address: str
    #: XRP only: numeric destination tag the customer MUST include in the transfer (the "tag/memo
    #: of the recipient" field on an exchange or in a wallet). Empty on other networks.
    destination_tag: str
    #: XLM (Stellar) only: numeric memo (type ID) the customer MUST include in the transfer — the
    #: "memo" field on an exchange or in a wallet. Empty on other networks.
    memo: str
    #: XRP only: the same details in one string in X-address format (XLS-5) — address and tag
    #: together; the QR encodes it as well. Empty on other networks.
    address_xaddress: str
    #: XLM only: the same details in one string — muxed address M… (SEP-23), address and memo
    #: together; the QR encodes it as well. Empty on other networks.
    address_muxed: str
    #: Address QR code as a PNG data: URI — can be used directly in <img src>. On XRP it encodes
    #: the X-address (address+tag in one string).
    address_qr_code: str
    #: true — this is a currency-agnostic link, the customer has not chosen a currency/network yet.
    is_multi: bool
    #: Link to the hosted payment page.
    url: str
    #: "Back to shop" link shown before payment.
    url_return: str
    #: Where to redirect after successful payment.
    url_success: str
    #: When the invoice expires (ISO 8601, like all time fields).
    expired_at: Timestamp
    #: When the rate will be refreshed (ISO 8601; the rate holds for ~5 min).
    rate_expires_at: Timestamp
    #: Current number of confirmations of the incoming payment.
    confirmations: int
    #: How many confirmations are needed for crediting (depends on the amount and the network).
    required_confirmations: int
    #: Hash of the incoming transaction (once it is seen).
    txid: str
    #: Creation time (ISO 8601).
    created_at: Timestamp
    #: Time of the last change (ISO 8601).
    updated_at: Timestamp


PUBLIC_PAYMENT_KEYS: Tuple[str, ...] = (
    "uuid",
    "order_id",
    "status",
    "is_final",
    "amount",
    "currency",
    "network",
    "payer_amount",
    "payer_currency",
    "amount_paid",
    "amount_remaining",
    "address",
    "destination_tag",
    "memo",
    "address_xaddress",
    "address_muxed",
    "address_qr_code",
    "is_multi",
    "url",
    "url_return",
    "url_success",
    "expired_at",
    "rate_expires_at",
    "confirmations",
    "required_confirmations",
    "txid",
    "created_at",
    "updated_at",
)


class QrCode(TypedDict):
    """`/v1/payment/qr` and `GET /v1/pay/{id}/qr`. All fields are empty while the invoice has no
    real address: sandbox invoices (synthetic `sandbox:` address) and `select` invoices awaiting
    a network."""

    #: `data:image/png;base64,…`
    image: str
    #: What the QR encodes: a payment URI when `is_uri`, else the bare address.
    payload: str
    is_uri: bool
    address: str


QR_CODE_KEYS: Tuple[str, ...] = ("image", "payload", "is_uri", "address")


class ResolutionAccepted(TypedDict):
    """`/v1/payment/resolve` with `action: "accept"` — the underpayment was kept as full
    settlement."""

    resolution: Literal["accepted"]
    payment_uuid: str
    order_id: str
    currency: str
    amount_kept: Money


RESOLUTION_ACCEPTED_KEYS: Tuple[str, ...] = (
    "resolution",
    "payment_uuid",
    "order_id",
    "currency",
    "amount_kept",
)


class _ResolutionRefundedRequired(_PayoutRequired):
    #: Always `"refunded"` — the underpayment was sent back.
    resolution: Literal["refunded"]


class ResolutionRefunded(_ResolutionRefundedRequired, total=False):
    """`/v1/payment/resolve` with `action: "refund"` — the underpayment was sent back; the body is
    the refund payout itself plus `resolution`."""

    #: Human-readable failure reason (failed payouts only).
    error: Optional[str]
    #: Machine-readable failure code (failed payouts only).
    error_code: Optional[str]
    #: Set on refunds of blocked static-wallet deposits.
    wallet_uuid: str


#: `/v1/payment/resolve` answers with one of the two shapes, told apart by `resolution`.
Resolution = Union[ResolutionAccepted, ResolutionRefunded]


class EmailSent(TypedDict):
    """`/v1/payment/send-email`."""

    ok: bool
    email: str
    uuid: str


EMAIL_SENT_KEYS: Tuple[str, ...] = ("ok", "email", "uuid")
