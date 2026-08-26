"""Outgoing transfers to external addresses. Every route here needs the payout key."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/payouts.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union, cast

from ...contract.models import (
    BatchElement,
    BatchSubmitted,
    Payout,
    PayoutCalculation,
    PayoutFeeConfig,
    PayoutValidation,
    RefundFeeConfig,
    ServiceMethod,
)
from ...contract.requests import (
    PayoutBatchBody,
    PayoutBody,
    PayoutCalculateBody,
    PayoutFeeConfigSetBody,
    PayoutHistoryBody,
    PayoutMassBody,
    PayoutRefundFeeConfigSetBody,
    PayoutServicesBody,
    PayoutValidateBody,
)
from ...core.pagination import AsyncPage
from ..base import AsyncResource

__all__ = ["AsyncPayouts", "PayoutLookup"]

#: Identify a payout by its ``uuid`` or by your ``order_id`` - a bare string is the uuid.
PayoutLookup = Union[str, Mapping[str, str]]


class AsyncPayouts(AsyncResource):
    """Payouts. Payout key."""

    async def create(self, params: PayoutBody, **options: Any) -> Payout:
        """``POST /v1/payout`` - create and (for API keys) auto-approve a payout.

        Idempotent by ``order_id`` and ``Idempotency-Key``.

        Codes worth branching on: ``payout.insufficient_funds`` (retryable - top up and repeat
        with the SAME key), ``payout.funds_maturing`` (retryable - deposits not yet mature),
        ``payout.bad_address``, ``payout.address_network_mismatch``, ``payout.memo_required``,
        ``payout.amount_below_fee``, ``payout.frozen``, ``payout.order_id_required``,
        ``idempotency.key_reused``, ``merchant.wrong_key_kind`` (a payment key on a payout route).
        """
        return cast(Payout, await self._call("POST /v1/payout", params, **options))

    async def validate(self, params: PayoutValidateBody, **options: Any) -> PayoutValidation:
        """``POST /v1/payout/validate`` - dry run: every check of :meth:`create`, nothing reserved."""
        return cast(
            PayoutValidation, await self._call("POST /v1/payout/validate", params, **options)
        )

    async def calculate(self, params: PayoutCalculateBody, **options: Any) -> PayoutCalculation:
        """``POST /v1/payout/calculate`` - commission and net amount without creating anything."""
        return cast(
            PayoutCalculation, await self._call("POST /v1/payout/calculate", params, **options)
        )

    async def info(self, lookup: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/info`` - by ``uuid`` or ``order_id``.

        Refunds are payouts too (``is_refund``).
        """
        return cast(Payout, await self._call("POST /v1/payout/info", by_uuid(lookup), **options))

    async def get(self, lookup: PayoutLookup, **options: Any) -> Payout:
        """Alias of :meth:`info`."""
        return cast(Payout, await self._call("POST /v1/payout/info", by_uuid(lookup), **options))

    async def cancel(self, payout: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/cancel`` - cancel while not yet broadcast.

        409 ``payout.not_pending`` once it left for the chain.
        """
        return cast(
            Payout, await self._call("POST /v1/payout/cancel", {"uuid": uuid_of(payout)}, **options)
        )

    async def approve(self, payout: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/approve`` - approve a payout awaiting manual approval."""
        return cast(
            Payout,
            await self._call("POST /v1/payout/approve", {"uuid": uuid_of(payout)}, **options),
        )

    def history(
        self, params: Optional[PayoutHistoryBody] = None, **options: Any
    ) -> AsyncPage[Payout]:
        """``POST /v1/payout/history`` - newest first. ``kind="refund"`` lists refunds only."""
        return self._page("POST /v1/payout/history", params, **options)

    def list(self, params: Optional[PayoutHistoryBody] = None, **options: Any) -> AsyncPage[Payout]:
        """Alias of :meth:`history`."""
        return self._page("POST /v1/payout/history", params, **options)

    async def mass(self, params: PayoutMassBody, **options: Any) -> Dict[str, List[BatchElement]]:
        """``POST /v1/payout/mass`` - SYNCHRONOUS batch (<=100).

        Each element reports its own outcome in ``items``, so a call that returns 200 can still
        contain failures - check every ``items[i]["ok"]``.

        Call-level codes worth branching on: ``payout.batch_too_large`` (more than 100),
        ``payout.empty_batch``, ``payout.insufficient_funds`` (retryable), ``payout.frozen``,
        ``merchant.wrong_key_kind``. Per-element failures arrive as ``items[i]["error_code"]``
        with the same vocabulary as :meth:`create`.
        """
        return cast(
            Dict[str, List[BatchElement]],
            await self._call("POST /v1/payout/mass", params, **options),
        )

    async def batch(self, params: PayoutBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/payout/batch`` - ASYNCHRONOUS batch (<=5000); poll ``batches.info``.

        ``order_id`` is required on every item.

        Codes worth branching on: ``payout.batch_too_large``, ``payout.empty_batch``,
        ``payout.order_id_required``, ``payout.reference_collision``, ``payout.frozen``,
        ``merchant.wrong_key_kind``, ``idempotency.key_reused``. Insufficient funds surface per
        element while the batch runs, not on submission.
        """
        return cast(BatchSubmitted, await self._call("POST /v1/payout/batch", params, **options))

    def services(
        self, params: Optional[PayoutServicesBody] = None, **options: Any
    ) -> AsyncPage[ServiceMethod]:
        """``POST /v1/payout/services`` - currencies/networks available for payouts."""
        return self._page("POST /v1/payout/services", params, **options)

    async def get_fee_config(self, **options: Any) -> PayoutFeeConfig:
        """``POST /v1/payout/fee-config/get``."""
        return cast(PayoutFeeConfig, await self._call("POST /v1/payout/fee-config/get", **options))

    async def set_fee_config(
        self, params: PayoutFeeConfigSetBody, **options: Any
    ) -> PayoutFeeConfig:
        """``POST /v1/payout/fee-config/set`` - who bears the network fee by default."""
        return cast(
            PayoutFeeConfig, await self._call("POST /v1/payout/fee-config/set", params, **options)
        )

    async def get_refund_fee_config(self, **options: Any) -> RefundFeeConfig:
        """``POST /v1/payout/refund-fee-config/get``."""
        return cast(
            RefundFeeConfig, await self._call("POST /v1/payout/refund-fee-config/get", **options)
        )

    async def set_refund_fee_config(
        self, params: PayoutRefundFeeConfigSetBody, **options: Any
    ) -> RefundFeeConfig:
        """``POST /v1/payout/refund-fee-config/set`` - who bears the fee on refunds."""
        return cast(
            RefundFeeConfig,
            await self._call("POST /v1/payout/refund-fee-config/set", params, **options),
        )


def by_uuid(ref: PayoutLookup) -> Dict[str, str]:
    """A bare string is taken as the ``uuid``."""
    return {"uuid": ref} if isinstance(ref, str) else dict(ref)


def uuid_of(ref: PayoutLookup) -> str:
    """The ``uuid`` of a payout given as a string or a mapping."""
    return ref if isinstance(ref, str) else ref["uuid"]
