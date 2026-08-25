"""Payouts, refunds, payout pricing, internal transfers and the fee-config toggles."""

from __future__ import annotations

from typing import Literal, Optional, Tuple, TypedDict, Union

from ..enums import FeeBearerResult, PayoutStatus
from .common import Money, Timestamp


class _PayoutRequired(TypedDict):
    #: Payout id.
    uuid: str
    #: Your payout number (reference). null for a refund: a refund has no identifier of yours,
    #: see payment_order_id.
    order_id: Optional[str]
    #: Coarse status: check (created, waiting) | process (being sent/waiting for confirmations) |
    #: paid (confirmed — done) | awaiting_cosign (waiting for the second signature) | fail |
    #: cancel.
    status: PayoutStatus
    #: true — the status is final (paid / fail / cancel).
    is_final: bool
    #: Payout amount in currency, debited from your balance.
    amount: Money
    #: Payout currency code.
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: Recipient address.
    address: str
    #: Destination tag/memo passed at creation (TON Jetton, exchange memo). Empty — no memo.
    memo: str
    #: How much actually goes to the recipient's address: amount − commission.
    payer_amount: Money
    #: Network fee withheld, in the payout currency. 0 — the gateway absorbed the fee.
    commission: Money
    #: Who paid the network fee: gateway — the gateway absorbed it (commission = 0); merchant —
    #: the debited amount was increased by the fee and the recipient receives the requested amount
    #: in full (is_subtract=true, payout link with fee_bearer=merchant); recipient — the fee was
    #: withheld from the payout and the recipient receives less than requested.
    fee_bearer: FeeBearerResult
    #: api (via the integration) | manual (from the cabinet).
    source: str
    #: true — the payout is awaiting approval (internal scenarios; always false for an API key).
    approval_required: bool
    #: true — this is a payment refund, not a regular payout.
    is_refund: bool
    #: Id of the payment being refunded (null if this is not a refund).
    refund_for: Optional[str]
    #: Your order_id of the payment the refund was made for (null for a regular payout). A refund
    #: has no order_id of its own — it comes back null, and a refund must be reconciled with the
    #: order by this field.
    payment_order_id: Optional[str]
    #: On-chain transaction hash (appears after sending).
    txid: str
    #: Signed link to the PDF cheque for this operation — opens without an API key, can be
    #: attached to an email or handed to the recipient. Empty if document generation is disabled.
    document_url: str
    #: Creation time (ISO 8601).
    created_at: Timestamp
    #: Time of the last change (ISO 8601).
    updated_at: Timestamp


class Payout(_PayoutRequired, total=False):
    """Payout as `/v1/payout`, `/info`, `/history`, `/cancel`, mass/batch elements and refunds
    render it (core `PayoutResult`). `error`/`error_code` appear on `info` for failed payouts."""

    #: Human-readable failure reason (failed payouts only).
    error: Optional[str]
    #: Machine-readable failure code (failed payouts only).
    error_code: Optional[str]
    #: Set on refunds of blocked static-wallet deposits.
    wallet_uuid: str


PAYOUT_KEYS: Tuple[str, ...] = (
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
)


class PayoutCalculation(TypedDict):
    """`/v1/payout/calculate`. Amounts are null when the asset cannot be priced right now."""

    amount: Optional[Money]
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    commission: Optional[Money]
    payer_amount: Optional[Money]
    fee_bearer: FeeBearerResult
    #: Pricing mode of the fee (`percent`/`fixed`/`exact`/…).
    fee_type: str


PAYOUT_CALCULATION_KEYS: Tuple[str, ...] = (
    "amount",
    "currency",
    "network",
    "commission",
    "payer_amount",
    "fee_bearer",
    "fee_type",
)


class _PayoutValidationRequired(TypedDict):
    valid: bool
    amount: Money
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    commission: Money
    payer_amount: Money
    fee_bearer: FeeBearerResult
    #: Non-empty when part of the balance is still maturing (reorg window).
    maturity_note: str


class PayoutValidation(_PayoutValidationRequired, total=False):
    """`/v1/payout/validate` — the dry run; errors are the same the create call would raise."""

    #: Which balance would fund it (`business`/`personal`), when reported.
    funded_by: str


PAYOUT_VALIDATION_KEYS: Tuple[str, ...] = (
    "valid",
    "amount",
    "currency",
    "network",
    "commission",
    "payer_amount",
    "fee_bearer",
    "maturity_note",
)


class TransferToPersonal(TypedDict):
    """`/v1/transfer/to-personal`: business → the owner's personal balance."""

    uuid: str
    currency: str
    amount: Money
    direction: Literal["to_personal"]
    #: Personal balance after the transfer.
    personal_balance: Money
    document_url: str


TRANSFER_TO_PERSONAL_KEYS: Tuple[str, ...] = (
    "uuid",
    "currency",
    "amount",
    "direction",
    "personal_balance",
    "document_url",
)


class TransferToUser(TypedDict):
    """`/v1/transfer/to-user`: business → another user's personal balance."""

    uuid: str
    currency: str
    amount: Money
    to_user_id: str
    document_url: str


TRANSFER_TO_USER_KEYS: Tuple[str, ...] = (
    "uuid",
    "currency",
    "amount",
    "to_user_id",
    "document_url",
)

#: Either side of the internal transfer pair, told apart by `direction`/`to_user_id`.
Transfer = Union[TransferToPersonal, TransferToUser]


class _PayoutFeeConfigRequired(TypedDict):
    fee_on_recipient: bool


class PayoutFeeConfig(_PayoutFeeConfigRequired, total=False):
    """`/v1/payout/fee-config/*` — who bears the network fee on payouts."""

    #: `get` only.
    configured: bool


PAYOUT_FEE_CONFIG_KEYS: Tuple[str, ...] = ("fee_on_recipient", "configured")


class _RefundFeeConfigRequired(TypedDict):
    fee_on_customer: bool


class RefundFeeConfig(_RefundFeeConfigRequired, total=False):
    """`/v1/payout/refund-fee-config/*` — who bears the network fee on refunds."""

    #: `get` only.
    configured: bool


REFUND_FEE_CONFIG_KEYS: Tuple[str, ...] = ("fee_on_customer", "configured")


class _PaymentFeeConfigRequired(TypedDict):
    payer_pays_percent: int


class PaymentFeeConfig(_PaymentFeeConfigRequired, total=False):
    """`/v1/payment/fee-config/*` — how much of the payment fee the payer absorbs."""

    #: `get` only.
    enabled: bool


PAYMENT_FEE_CONFIG_KEYS: Tuple[str, ...] = ("payer_pays_percent", "enabled")
