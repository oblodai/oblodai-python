"""Asynchronous batch progress, and internal transfers between platform balances."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/batches.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, cast

from ...contract.models import BatchInfo, BatchSubmitted, TransferToPersonal, TransferToUser
from ...contract.requests import (
    BatchInfoBody,
    TransferBatchBody,
    TransferToPersonalBody,
    TransferToUserBody,
)
from ...core.errors import PermissionError as OblodaiPermissionError
from ..base import AsyncResource

__all__ = ["AsyncBatches", "AsyncTransfers"]


class AsyncBatches(AsyncResource):
    """Progress of asynchronous batches (payment, refund, payout, transfer, payout-link)."""

    async def info(self, params: BatchInfoBody, **options: Any) -> BatchInfo:
        """``POST /v1/batch/info`` - status, counters and per-row outcomes.

        Accepts either key kind; the core requires the kind that created the batch, so a payout
        batch is retried with the payout key when one is configured.
        """
        try:
            return cast(BatchInfo, await self._call("POST /v1/batch/info", params, **options))
        except OblodaiPermissionError as err:
            if err.code != "merchant.wrong_key_kind" or options.get("prefer_payout_key"):
                raise
        retry = dict(options)
        retry["prefer_payout_key"] = True
        return cast(BatchInfo, await self._call("POST /v1/batch/info", params, **retry))


class AsyncTransfers(AsyncResource):
    """Internal, instant, fee-free moves between platform balances. Payout key."""

    async def to_personal(
        self, params: TransferToPersonalBody, **options: Any
    ) -> TransferToPersonal:
        """``POST /v1/transfer/to-personal`` - business balance to the owner's personal wallet."""
        return cast(
            TransferToPersonal, await self._call("POST /v1/transfer/to-personal", params, **options)
        )

    async def to_user(self, params: TransferToUserBody, **options: Any) -> TransferToUser:
        """``POST /v1/transfer/to-user`` - business balance to another platform user's wallet.

        ``amount`` and ``currency`` are required.
        """
        return cast(
            TransferToUser, await self._call("POST /v1/transfer/to-user", params, **options)
        )

    async def batch(self, params: TransferBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/transfer/batch`` - ASYNCHRONOUS batch of :meth:`to_user` transfers.

        Poll ``batches.info``; ``order_id`` is required on every item.
        """
        return cast(BatchSubmitted, await self._call("POST /v1/transfer/batch", params, **options))
