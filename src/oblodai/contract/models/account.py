"""Balances, referrals, static wallets, per-merchant settings, split rules and document jobs."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, TypedDict

from .common import Money, Timestamp


class BalanceEntry(TypedDict):
    """One asset line of the merchant balance."""

    currency: str
    #: Available (spendable) balance.
    balance: Money


class BalanceBlock(TypedDict):
    """The `balance` block of `/v1/balance`."""

    #: Per-asset available balances of the business account.
    merchant: List[BalanceEntry]


class Balance(TypedDict):
    """`/v1/balance`."""

    balance: BalanceBlock


BALANCE_KEYS: Tuple[str, ...] = ("balance",)


class ReferralWeek(TypedDict):
    """Rolling seven-day slice of `/v1/referral/info`."""

    referred_count: int
    earnings_by_asset: Dict[str, Money]


class ReferralInfo(TypedDict):
    """`/v1/referral/info`."""

    #: The merchant's referral code.
    code: str
    #: Invitation link carrying the code.
    link: str
    #: Referral tiers, basis points.
    tier_bps: List[int]
    #: How many merchants signed up through the link.
    referred_count: int
    #: Lifetime referral earnings, keyed by asset.
    earnings_by_asset: Dict[str, Money]
    #: The same counters over the last seven days.
    week: ReferralWeek


REFERRAL_INFO_KEYS: Tuple[str, ...] = (
    "code",
    "link",
    "tier_bps",
    "referred_count",
    "earnings_by_asset",
    "week",
)


class VrcsStatus(TypedDict):
    """`/v1/vrcs` — volatility risk control (auto-convert volatile deposits to USDT)."""

    enabled: bool


VRCS_STATUS_KEYS: Tuple[str, ...] = ("enabled",)


class _WalletRequired(TypedDict):
    #: Static wallet id.
    uuid: str
    #: Permanent address for top-ups. On XRP it is the classic r-address of the SHARED wallet; a
    #: top-up must carry destination_tag.
    address: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: Top-up currency.
    currency: str
    #: Your customer identifier the address is pinned to (part of the currency+network+order_id
    #: idempotency triple).
    order_id: str
    #: Reserved (usually empty).
    url: str
    #: Signed link to the PDF with the address and its QR. Empty if document generation is not
    #: enabled.
    document_url: str


class Wallet(_WalletRequired, total=False):
    """Static (permanent) deposit wallet — `/v1/wallet`."""

    #: XRP only: numeric destination tag of this wallet — the customer must include it in every
    #: transfer.
    destination_tag: str
    #: XLM only: numeric memo (type ID) of this wallet — the customer must include it in every
    #: transfer.
    memo: str
    #: XRP only: address and tag in one string (X-address, XLS-5).
    address_xaddress: str
    #: XLM only: address and memo in one string (muxed M…, SEP-23).
    address_muxed: str


WALLET_KEYS: Tuple[str, ...] = (
    "uuid",
    "address",
    "network",
    "currency",
    "order_id",
    "url",
    "document_url",
)


class WalletBlocked(TypedDict):
    """`/v1/wallet/block`."""

    uuid: str
    address: str
    blocked: bool


WALLET_BLOCKED_KEYS: Tuple[str, ...] = ("uuid", "address", "blocked")


class WalletQr(TypedDict):
    """`/v1/wallet/qr` — the address QR as a data URI."""

    #: `data:image/png;base64,…`
    image: str


class AutoWithdrawRule(TypedDict):
    """`/v1/auto-withdraw/*` entry."""

    currency: str
    #: Network of the destination address. Vocabulary: `Network`.
    network: str
    #: Destination address (the merchant's external wallet).
    address: str
    #: Sweep only once the balance reaches this much.
    min_amount: Money


AUTO_WITHDRAW_RULE_KEYS: Tuple[str, ...] = ("currency", "network", "address", "min_amount")


class ApiAllowlist(TypedDict):
    """`/v1/api-allowlist/*` — entries are CIDRs."""

    #: true — accept API calls only from listed addresses.
    enabled: bool
    #: The listed IPs and subnets in CIDR notation.
    items: List[str]


API_ALLOWLIST_KEYS: Tuple[str, ...] = ("enabled", "items")


class DiscountRule(TypedDict):
    """`/v1/payment/discount/*` entry — a per-method price adjustment."""

    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: Positive = discount for the payer, negative = markup.
    discount_percent: int


DISCOUNT_RULE_KEYS: Tuple[str, ...] = ("currency", "network", "discount_percent")


class AccuracyConfig(TypedDict):
    """`/v1/payment/accuracy/*` — the underpayment tolerance."""

    enabled: bool
    #: How much less than due still counts as paid, in percent.
    accuracy_percent: int


ACCURACY_CONFIG_KEYS: Tuple[str, ...] = ("enabled", "accuracy_percent")


class _AutoRefundConfigRequired(TypedDict):
    #: Refund overpayments automatically.
    overpay: bool
    #: Refund underpayments automatically.
    underpay: bool


class AutoRefundConfig(_AutoRefundConfigRequired, total=False):
    """`/v1/payment/autorefund/*` — automatic handling of over- and underpayments."""

    #: `get` only: whether the merchant ever set it.
    configured: bool


AUTO_REFUND_CONFIG_KEYS: Tuple[str, ...] = ("overpay", "underpay", "configured")


class _AcceptedMethodRequired(TypedDict):
    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: true — the method is offered on the pay page right now.
    available: bool


class AcceptedMethod(_AcceptedMethodRequired, total=False):
    """`/v1/payment/accepted/list` entry — a currency/network the merchant accepts."""

    #: Why it is unavailable, when it is.
    reason: str


ACCEPTED_METHOD_KEYS: Tuple[str, ...] = ("currency", "network", "available")


class _SplitRuleRequired(TypedDict):
    rule_id: str
    #: Share of every payment, percent, as a decimal string.
    percent: str


class SplitRule(_SplitRuleRequired, total=False):
    """`/v1/split/rule` and `/v1/split/rule/list` items."""

    #: false — the rule is kept but not applied.
    active: bool
    #: Off-platform destination address the share is sent to.
    address: str
    #: Network of `address`. Vocabulary: `Network`.
    network: str
    #: Set for on-platform partner rules (reversible on refund).
    merchant_id: str
    #: Free-form label.
    note: str
    #: true — the share is clawed back when the payment is refunded.
    reversible: bool


SPLIT_RULE_KEYS: Tuple[str, ...] = (
    "rule_id",
    "percent",
    "active",
    "address",
    "network",
    "note",
    "reversible",
)

#: `POST /v1/split/rule` answers with the id and percent only.
SPLIT_RULE_CREATED_KEYS: Tuple[str, ...] = ("rule_id", "percent")


class SplitConfig(TypedDict):
    """`/v1/split/config/*` — how long partner shares are held back for refunds."""

    refund_hold_seconds: int


SPLIT_CONFIG_KEYS: Tuple[str, ...] = ("refund_hold_seconds",)


class SplitOptIn(TypedDict):
    """`/v1/split/recipient/optin*` — whether this merchant accepts partner shares."""

    enabled: bool


SPLIT_OPT_IN_KEYS: Tuple[str, ...] = ("enabled",)


_DocumentJobPeriodFields = TypedDict(
    "_DocumentJobPeriodFields",
    {
        # Inclusive start of the reporting window, YYYY-MM-DD.
        "from": str,
        # Inclusive end of the reporting window, YYYY-MM-DD.
        "to": str,
    },
)


class DocumentJobPeriod(_DocumentJobPeriodFields):
    """Reporting window of a document job (`from` is a Python keyword — read it as
    ``period["from"]``)."""


class DocumentJobFile(TypedDict):
    """The rendered artefact of a finished document job."""

    #: Signed link to the file, or use `documents.jobFile`.
    download_url: str
    #: When the link stops working.
    expires_at: Timestamp
    #: Rows in the report.
    rows: int
    #: Size of the file in bytes.
    size_bytes: int


class _DocumentJobRequired(TypedDict):
    job_id: str
    #: What was ordered (`statement`, `ledger`, …).
    kind: str
    #: Rendering format (`csv`, `pdf`, …).
    format: str
    #: Language of the rendered document.
    lang: str
    #: Job status: queued | processing | done | failed.
    status: str
    #: Reporting window.
    period: DocumentJobPeriod
    created_at: Timestamp
    updated_at: Timestamp


class DocumentJob(_DocumentJobRequired, total=False):
    """`/v1/documents/jobs` and `/jobs/info`."""

    #: Human hint while queued (e.g. "15s").
    ready_within: str
    #: Set once done; `download_url` is a signed link, or use `documents.jobFile`.
    file: DocumentJobFile
    #: Why the job failed, when it did.
    error: Optional[str]


DOCUMENT_JOB_KEYS: Tuple[str, ...] = (
    "job_id",
    "kind",
    "format",
    "lang",
    "status",
    "period",
    "created_at",
    "updated_at",
)
