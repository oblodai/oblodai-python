"""Outgoing transfers to external addresses. Every route here needs the payout key."""

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
    """Payouts. Payout key."""

    def create(self, params: PayoutBody, **options: Any) -> Payout:
        """``POST /v1/payout`` - create and (for API keys) auto-approve a payout.

        Idempotent by ``order_id`` and ``Idempotency-Key``. Errors worth handling:
        ``payout.insufficient_funds`` (retryable), ``payout.funds_maturing``,
        ``payout.bad_address``, ``payout.memo_required``.
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

        Each element reports its own outcome in ``items``.
        """
        return cast(
            Dict[str, List[BatchElement]], self._call("POST /v1/payout/mass", params, **options)
        )

    def batch(self, params: PayoutBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/payout/batch`` - ASYNCHRONOUS batch (<=5000); poll ``batches.info``.

        ``order_id`` is required on every item.
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
