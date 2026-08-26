"""Outgoing transfers to external addresses."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union, cast

from ..contract.models import (
    BatchElement,
    BatchSubmitted,
    Payout,
    PayoutCalculation,
    PayoutFeeConfig,
    PayoutValidation,
    RefundFeeConfig,
    ServiceMethod,
)
from ..contract.requests import (
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
from ..core.pagination import Page
from .base import Resource

__all__ = ["PayoutLookup", "Payouts"]

#: Identify a payout by its ``uuid`` or by your ``order_id`` - a bare string is the uuid.
PayoutLookup = Union[str, Mapping[str, str]]


class Payouts(Resource):
    """Payouts."""

    def create(self, params: PayoutBody, **options: Any) -> Payout:
        """``POST /v1/payout`` - create and (for API keys) auto-approve a payout.

        Idempotent by ``order_id`` and ``Idempotency-Key``.

        Codes worth branching on: ``payout.insufficient_funds`` (retryable - top up and repeat
        with the SAME key), ``payout.funds_maturing`` (retryable - deposits not yet mature),
        ``payout.bad_address``, ``payout.address_network_mismatch``, ``payout.memo_required``,
        ``payout.amount_below_fee``, ``payout.frozen``, ``payout.order_id_required``,
        ``idempotency.key_reused``.
        """
        return cast(Payout, self._call("POST /v1/payout", params, **options))

    def validate(self, params: PayoutValidateBody, **options: Any) -> PayoutValidation:
        """``POST /v1/payout/validate`` - dry run: every check of :meth:`create`, nothing reserved."""
        return cast(PayoutValidation, self._call("POST /v1/payout/validate", params, **options))

    def calculate(self, params: PayoutCalculateBody, **options: Any) -> PayoutCalculation:
        """``POST /v1/payout/calculate`` - commission and net amount without creating anything."""
        return cast(PayoutCalculation, self._call("POST /v1/payout/calculate", params, **options))

    def info(self, lookup: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/info`` - by ``uuid`` or ``order_id``.

        Refunds are payouts too (``is_refund``).
        """
        return cast(Payout, self._call("POST /v1/payout/info", by_uuid(lookup), **options))

    def get(self, lookup: PayoutLookup, **options: Any) -> Payout:
        """Alias of :meth:`info`."""
        return cast(Payout, self._call("POST /v1/payout/info", by_uuid(lookup), **options))

    def cancel(self, payout: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/cancel`` - cancel while not yet broadcast.

        409 ``payout.not_pending`` once it left for the chain.
        """
        return cast(
            Payout, self._call("POST /v1/payout/cancel", {"uuid": uuid_of(payout)}, **options)
        )

    def approve(self, payout: PayoutLookup, **options: Any) -> Payout:
        """``POST /v1/payout/approve`` - approve a payout awaiting manual approval."""
        return cast(
            Payout, self._call("POST /v1/payout/approve", {"uuid": uuid_of(payout)}, **options)
        )

    def history(self, params: Optional[PayoutHistoryBody] = None, **options: Any) -> Page[Payout]:
        """``POST /v1/payout/history`` - newest first. ``kind="refund"`` lists refunds only."""
        return self._page("POST /v1/payout/history", params, **options)

    def list(self, params: Optional[PayoutHistoryBody] = None, **options: Any) -> Page[Payout]:
        """Alias of :meth:`history`."""
        return self._page("POST /v1/payout/history", params, **options)

    def mass(self, params: PayoutMassBody, **options: Any) -> Dict[str, List[BatchElement]]:
        """``POST /v1/payout/mass`` - SYNCHRONOUS batch (<=100).

        Each element reports its own outcome in ``items``, so a call that returns 200 can still
        contain failures - check every ``items[i]["ok"]``.

        Call-level codes worth branching on: ``payout.batch_too_large`` (more than 100),
        ``payout.empty_batch``, ``payout.insufficient_funds`` (retryable), ``payout.frozen``.
        Per-element failures arrive as ``items[i]["error_code"]``
        with the same vocabulary as :meth:`create`.
        """
        return cast(
            Dict[str, List[BatchElement]], self._call("POST /v1/payout/mass", params, **options)
        )

    def batch(self, params: PayoutBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/payout/batch`` - ASYNCHRONOUS batch (<=5000); poll ``batches.info``.

        ``order_id`` is required on every item.

        Codes worth branching on: ``payout.batch_too_large``, ``payout.empty_batch``,
        ``payout.order_id_required``, ``payout.reference_collision``, ``payout.frozen``,
        ``idempotency.key_reused``. Insufficient funds surface per
        element while the batch runs, not on submission.
        """
        return cast(BatchSubmitted, self._call("POST /v1/payout/batch", params, **options))

    def services(
        self, params: Optional[PayoutServicesBody] = None, **options: Any
    ) -> Page[ServiceMethod]:
        """``POST /v1/payout/services`` - currencies/networks available for payouts."""
        return self._page("POST /v1/payout/services", params, **options)

    def get_fee_config(self, **options: Any) -> PayoutFeeConfig:
        """``POST /v1/payout/fee-config/get``."""
        return cast(PayoutFeeConfig, self._call("POST /v1/payout/fee-config/get", **options))

    def set_fee_config(self, params: PayoutFeeConfigSetBody, **options: Any) -> PayoutFeeConfig:
        """``POST /v1/payout/fee-config/set`` - who bears the network fee by default."""
        return cast(
            PayoutFeeConfig, self._call("POST /v1/payout/fee-config/set", params, **options)
        )

    def get_refund_fee_config(self, **options: Any) -> RefundFeeConfig:
        """``POST /v1/payout/refund-fee-config/get``."""
        return cast(RefundFeeConfig, self._call("POST /v1/payout/refund-fee-config/get", **options))

    def set_refund_fee_config(
        self, params: PayoutRefundFeeConfigSetBody, **options: Any
    ) -> RefundFeeConfig:
        """``POST /v1/payout/refund-fee-config/set`` - who bears the fee on refunds."""
        return cast(
            RefundFeeConfig,
            self._call("POST /v1/payout/refund-fee-config/set", params, **options),
        )


def by_uuid(ref: PayoutLookup) -> Dict[str, str]:
    """A bare string is taken as the ``uuid``."""
    return {"uuid": ref} if isinstance(ref, str) else dict(ref)


def uuid_of(ref: PayoutLookup) -> str:
    """The ``uuid`` of a payout given as a string or a mapping."""
    return ref if isinstance(ref, str) else ref["uuid"]
