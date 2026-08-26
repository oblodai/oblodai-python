"""Payout links (cheques), their claim flow, and payment links."""

from __future__ import annotations

from typing import List, Optional, Tuple, TypedDict

from ..enums import AmountMode, FeeBearer, PaymentStatus, PayoutLinkStatus
from .common import Money, Timestamp


class _PayoutLinkRequired(TypedDict):
    #: Link id (use it in `/v1/payout/link/info`).
    link_id: str
    status: PayoutLinkStatus
    amount: Money
    currency: str
    #: Blockchain network the cheque pays out on. Vocabulary: `Network`.
    network: str
    #: Null while the asset cannot be priced.
    commission: Optional[Money]
    payer_amount: Optional[Money]
    fee_bearer: FeeBearer
    #: Pricing mode of the fee (`percent`/`fixed`/`exact`/…).
    fee_type: str
    #: Your reference for the cheque.
    reference: str
    title: str
    note: str
    passcode_protected: bool
    expires_at: Timestamp
    created_at: Timestamp


class PayoutLink(_PayoutLinkRequired, total=False):
    """Payout link (cheque) as `/v1/payout/link`, `/info`, `/list`, `/cancel` and batch elements
    render it."""

    #: Present on create and batch-create only — the secret the recipient claims with.
    claim_token: str
    #: The claim page URL carrying `claim_token` (create and batch-create only).
    claim_url: str
    #: Id of the batch the cheque was created in (batch-create only).
    batch_id: str
    #: Set once claimed: the payout that paid the recipient.
    payout_id: str
    #: Address the recipient claimed to, once claimed.
    claim_address: str
    #: Recipient e-mail, when the cheque was sent by mail.
    email: str
    #: The generated passcode, shown once on create when `passcode: "auto"` was requested.
    passcode: str


PAYOUT_LINK_KEYS: Tuple[str, ...] = (
    "link_id",
    "status",
    "amount",
    "currency",
    "network",
    "commission",
    "payer_amount",
    "fee_bearer",
    "fee_type",
    "reference",
    "title",
    "note",
    "passcode_protected",
    "expires_at",
    "created_at",
)


class ClaimPreview(TypedDict):
    """`GET /v1/claim/{token}` — what the recipient sees before claiming."""

    status: PayoutLinkStatus
    #: true — the cheque can be claimed right now.
    claimable: bool
    amount: Money
    currency: str
    #: Blockchain network the cheque pays out on. Vocabulary: `Network`.
    network: str
    #: Null while the asset cannot be priced.
    commission: Optional[Money]
    payer_amount: Optional[Money]
    fee_bearer: FeeBearer
    #: Pricing mode of the fee (`percent`/`fixed`/`exact`/…).
    fee_type: str
    title: str
    note: str
    expires_at: Timestamp


CLAIM_PREVIEW_KEYS: Tuple[str, ...] = (
    "status",
    "claimable",
    "amount",
    "currency",
    "network",
    "commission",
    "payer_amount",
    "fee_bearer",
    "fee_type",
    "title",
    "note",
    "expires_at",
)


class ClaimResult(TypedDict):
    """`POST /v1/claim/{token}` — the payout minted by a claim."""

    #: The payout that pays the recipient (`payouts.info({ uuid: payout_id })`).
    payout_id: str
    status: PayoutLinkStatus
    #: Address the funds were sent to.
    address: str
    amount: Money
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: Null while the asset cannot be priced.
    commission: Optional[Money]
    payer_amount: Optional[Money]
    fee_bearer: FeeBearer
    #: Pricing mode of the fee (`percent`/`fixed`/`exact`/…).
    fee_type: str


CLAIM_RESULT_KEYS: Tuple[str, ...] = (
    "payout_id",
    "status",
    "address",
    "amount",
    "currency",
    "network",
    "commission",
    "payer_amount",
    "fee_bearer",
    "fee_type",
)


class _PaymentLinkPaymentRequired(TypedDict):
    uuid: str
    amount: Money
    currency: str
    status: PaymentStatus
    created_at: Timestamp


class PaymentLinkPayment(_PaymentLinkPaymentRequired, total=False):
    """Invoice spawned by a payment link (`/v1/payment/link/info` only)."""

    #: Your order number, when the invoice carried one.
    order_id: str


class _PaymentLinkRequired(TypedDict):
    #: Link id.
    link_id: str
    #: Public URL of the payment page — give it to the buyer as a button, in an email or as a QR
    #: code.
    url: str
    active: bool
    title: str
    description: str
    amount_mode: AmountMode
    currency: str
    #: Signed link to a PDF poster with the payment QR (for printing at the till). Empty if
    #: document generation is not enabled.
    document_url: str
    created_at: Timestamp


class PaymentLink(_PaymentLinkRequired, total=False):
    """Payment link as `/v1/payment/link/info` and `/list` render it. Amount fields depend on
    `amount_mode`."""

    #: `fixed` links.
    amount_fixed: Money
    #: `range` links.
    min_amount: Money
    max_amount: Money
    #: Currency the link is pinned to, when it is.
    pinned_currency: str
    #: Network the link is pinned to, when it is. Vocabulary: `Network`.
    pinned_network: str
    expires_at: Timestamp
    #: `info` only: invoices spawned by this link.
    payments: List[PaymentLinkPayment]


#: Keys of a `fixed` link with a pinned network — the shape the golden body was recorded with.
PAYMENT_LINK_KEYS: Tuple[str, ...] = (
    "link_id",
    "url",
    "active",
    "title",
    "description",
    "amount_mode",
    "currency",
    "amount_fixed",
    "pinned_network",
    "expires_at",
    "document_url",
    "created_at",
)


class PaymentLinkCreated(TypedDict):
    """`POST /v1/payment/link` acknowledgement."""

    #: Link id.
    link_id: str
    #: Public URL of the payment page — give it to the buyer as a button, in an email or as a QR
    #: code.
    url: str
    #: Signed link to a PDF poster with the payment QR (for printing at the till). Empty if
    #: document generation is not enabled.
    document_url: str


PAYMENT_LINK_CREATED_KEYS: Tuple[str, ...] = ("link_id", "url", "document_url")


class PaymentLinkToggled(TypedDict):
    """`POST /v1/payment/link/toggle` — the link's new on/off state."""

    link_id: str
    active: bool


PAYMENT_LINK_TOGGLED_KEYS: Tuple[str, ...] = ("link_id", "active")


class _PublicPaymentLinkRequired(TypedDict):
    link_id: str
    title: str
    description: str
    amount_mode: AmountMode
    currency: str


class PublicPaymentLink(_PublicPaymentLinkRequired, total=False):
    """`GET /v1/link/{id}` — the payer-facing view of a payment link."""

    #: `fixed` links.
    amount_fixed: Money
    #: `range` links.
    min_amount: Money
    max_amount: Money
    #: Currency the link is pinned to, when it is.
    pinned_currency: str
    #: Network the link is pinned to, when it is. Vocabulary: `Network`.
    pinned_network: str


PUBLIC_PAYMENT_LINK_KEYS: Tuple[str, ...] = (
    "link_id",
    "title",
    "description",
    "amount_mode",
    "currency",
    "amount_fixed",
    "pinned_network",
)
