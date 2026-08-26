"""Service catalogues and batch acknowledgements - the shapes shared by payments and payouts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TypedDict

from ..enums import BatchOnError
from .common import BatchKind, BatchStatus, Money, Timestamp


class _ServiceLimitRequired(TypedDict):
    #: Lower bound, null when the asset cannot be priced right now.
    min_amount: Optional[Money]
    #: Upper bound, null when the asset cannot be priced right now.
    max_amount: Optional[Money]


class ServiceLimit(_ServiceLimitRequired, total=False):
    """Per-method amount limits of a `ServiceMethod`."""

    #: Currency the limits are expressed in.
    currency: str


class ServiceCommission(TypedDict):
    """Per-method pricing of a `ServiceMethod`."""

    #: Currency the fee is expressed in.
    currency: str
    #: Fixed part of the fee, null when the asset cannot be priced right now.
    fee_amount: Optional[Money]
    #: Percentage part of the fee, as a decimal string.
    percent: Optional[str]
    #: Pricing mode (`percent`/`fixed`/`exact`/…).
    fee_type: str


class ServiceMethod(TypedDict):
    """Item of `/v1/payment/services` and `/v1/payout/services`."""

    currency: str
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    is_available: bool
    #: Limits are null when the asset cannot be priced right now.
    limit: ServiceLimit
    commission: ServiceCommission


SERVICE_METHOD_KEYS: Tuple[str, ...] = (
    "currency",
    "network",
    "is_available",
    "limit",
    "commission",
)


class BatchSubmitted(TypedDict):
    """`/v1/payment/batch`, `/v1/refund/batch`, `/v1/payout/batch`, `/v1/transfer/batch`
    acknowledgement."""

    #: Batch id — use it in POST /v1/batch/info to get the status and the results.
    batch_id: str
    #: Batch kind: payment | refund | payout | transfer.
    kind: BatchKind
    #: Initial status — always pending.
    status: BatchStatus
    #: How many items were accepted for processing.
    count: int


BATCH_SUBMITTED_KEYS: Tuple[str, ...] = ("batch_id", "kind", "status", "count")


class _BatchInfoItemRequired(TypedDict):
    #: Index of the item in the original array (zero-based).
    idx: int
    #: Item status: pending | processing | done | error.
    status: str


class BatchInfoItem(_BatchInfoItemRequired, total=False):
    """One element of a `/v1/batch/info` page."""

    #: Item outcome: true when status is "done", false when status is "error"; absent while the
    #: item is not processed.
    ok: bool
    #: The item's order_id, if you set one; not always present.
    order_id: str
    #: Result of the successful operation — the same object a single call would return; only when
    #: status is "done".
    result: Dict[str, Any]
    #: Human-readable error message; only when status is "error".
    message: str
    #: Machine-readable error code — the same one a single call would return
    #: (payment.below_minimum, payout.address_network_mismatch, …); batch.stopped /
    #: batch.key_revoked — the item was not executed; only when status is "error". Empty for
    #: items completed before the field was introduced.
    error_code: str
    #: HTTP status a single call would have returned (400, 409, …); absent if the item never
    #: reached the handler (batch.stopped, batch.key_revoked).
    http_status: int


class BatchInfo(TypedDict):
    """`/v1/batch/info`."""

    #: Batch id.
    batch_id: str
    #: Batch kind: payment | refund | payout.
    kind: BatchKind
    #: Batch status: pending | processing | completed | stopped. TERMINAL states are completed AND
    #: stopped (poll until one of them, not only until completed): completed = processing reached
    #: the end, stopped = a batch with on_error=stop halted on the first error (the remaining
    #: items were skipped and counted in failed). Neither means "everything succeeded" — check
    #: succeeded/failed.
    status: BatchStatus
    #: Error handling mode the batch was submitted with: continue | stop.
    on_error: BatchOnError
    #: Total items in the batch; counted over the whole batch and independent of pagination.
    total: int
    #: Processed successfully.
    succeeded: int
    #: Failed with an error (with on_error stop, skipped items are counted here too).
    failed: int
    #: Page of items with the result or the error for each one.
    items: List[BatchInfoItem]
    #: Batch creation time (ISO 8601, UTC).
    created_at: Timestamp
    #: Time of the last change (ISO 8601, UTC).
    updated_at: Timestamp


BATCH_INFO_KEYS: Tuple[str, ...] = (
    "batch_id",
    "kind",
    "status",
    "on_error",
    "total",
    "succeeded",
    "failed",
    "items",
    "created_at",
    "updated_at",
)
