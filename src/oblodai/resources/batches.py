"""Asynchronous batch progress, and internal transfers between platform balances."""

from __future__ import annotations

from typing import Any, cast

from ..contract.models import BatchInfo, BatchSubmitted, TransferToPersonal, TransferToUser
from ..contract.requests import (
    BatchInfoBody,
    TransferBatchBody,
    TransferToPersonalBody,
    TransferToUserBody,
)
from .base import Resource

__all__ = ["Batches", "Transfers"]


class Batches(Resource):
    """Progress of asynchronous batches (payment, refund, payout, transfer, payout-link)."""

    def info(self, params: BatchInfoBody, **options: Any) -> BatchInfo:
        """``POST /v1/batch/info`` - status, counters and per-row outcomes.

        Signed with the merchant's API key, whatever kind of batch it was that created the rows.
        """
        return cast(BatchInfo, self._call("POST /v1/batch/info", params, **options))


class Transfers(Resource):
    """Internal, instant, fee-free moves between platform balances."""

    def to_personal(self, params: TransferToPersonalBody, **options: Any) -> TransferToPersonal:
        """``POST /v1/transfer/to-personal`` - business balance to the owner's personal wallet.

        Codes worth branching on: ``transfer.bad_amount``, ``payout.insufficient_funds``
        (retryable), ``payout.funds_maturing`` (retryable), ``merchant.no_personal_wallet``,
        ``idempotency.key_reused``.
        """
        return cast(
            TransferToPersonal, self._call("POST /v1/transfer/to-personal", params, **options)
        )

    def to_user(self, params: TransferToUserBody, **options: Any) -> TransferToUser:
        """``POST /v1/transfer/to-user`` - business balance to another platform user's wallet.

        ``amount`` and ``currency`` are required.

        Codes worth branching on: ``transfer.bad_amount``, ``transfer.bad_recipient``,
        ``transfer.no_recipient``, ``transfer.recipient_not_found``,
        ``payout.insufficient_funds`` (retryable), ``idempotency.key_reused``.
        """
        return cast(TransferToUser, self._call("POST /v1/transfer/to-user", params, **options))

    def batch(self, params: TransferBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/transfer/batch`` - ASYNCHRONOUS batch of :meth:`to_user` transfers.

        Poll ``batches.info``; ``order_id`` is required on every item.

        Codes worth branching on: ``payout.batch_too_large``, ``payout.empty_batch``,
        ``request.missing_field`` (an item without ``order_id``),
        ``transfer.recipient_not_found``, ``idempotency.key_reused``.
        """
        return cast(BatchSubmitted, self._call("POST /v1/transfer/batch", params, **options))
