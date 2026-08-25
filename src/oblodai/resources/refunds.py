"""Refunds are payouts in the invoice's own asset; underpayments are resolved (accept or refund)."""

from __future__ import annotations

from typing import Any, cast

from ..contract.models import BatchSubmitted, Payout, Resolution
from ..contract.requests import PaymentRefundBody, PaymentResolveBody, RefundBatchBody
from .base import Resource

__all__ = ["Refunds"]


class Refunds(Resource):
    """Refunds and underpayment resolution. Payout key."""

    def create(self, params: PaymentRefundBody, **options: Any) -> Payout:
        """``POST /v1/payment/refund`` - refund a paid invoice, fully or partially."""
        return cast(Payout, self._call("POST /v1/payment/refund", params, **options))

    def resolve(self, params: PaymentResolveBody, **options: Any) -> Resolution:
        """``POST /v1/payment/resolve`` - settle an underpaid (``wrong_amount``) invoice."""
        return cast(Resolution, self._call("POST /v1/payment/resolve", params, **options))

    def batch(self, params: RefundBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/refund/batch`` - up to 5000 refunds; track with ``batches.info``."""
        return cast(BatchSubmitted, self._call("POST /v1/refund/batch", params, **options))
