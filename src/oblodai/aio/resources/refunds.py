"""AsyncRefunds are payouts in the invoice's own asset; underpayments are resolved (accept or refund)."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/refunds.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, cast

from ...contract.models import BatchSubmitted, Payout, Resolution
from ...contract.requests import PaymentRefundBody, PaymentResolveBody, RefundBatchBody
from ..base import AsyncResource

__all__ = ["AsyncRefunds"]


class AsyncRefunds(AsyncResource):
    """AsyncRefunds and underpayment resolution. Payout key."""

    async def create(self, params: PaymentRefundBody, **options: Any) -> Payout:
        """``POST /v1/payment/refund`` - refund a paid invoice, fully or partially."""
        return cast(Payout, await self._call("POST /v1/payment/refund", params, **options))

    async def resolve(self, params: PaymentResolveBody, **options: Any) -> Resolution:
        """``POST /v1/payment/resolve`` - settle an underpaid (``wrong_amount``) invoice."""
        return cast(Resolution, await self._call("POST /v1/payment/resolve", params, **options))

    async def batch(self, params: RefundBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/refund/batch`` - up to 5000 refunds; track with ``batches.info``."""
        return cast(BatchSubmitted, await self._call("POST /v1/refund/batch", params, **options))
