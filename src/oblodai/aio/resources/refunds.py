"""Refunds are payouts in the invoice's own asset; underpayments are resolved (accept or refund)."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/refunds.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, cast

from ...contract.models import BatchSubmitted, Payout, Resolution
from ...contract.requests import PaymentRefundBody, PaymentResolveBody, RefundBatchBody
from ..base import AsyncResource

__all__ = ["AsyncRefunds"]


class AsyncRefunds(AsyncResource):
    """Refunds and underpayment resolution. Payout key."""

    async def create(self, params: PaymentRefundBody, **options: Any) -> Payout:
        """``POST /v1/payment/refund`` - refund a paid invoice, fully or partially. Payout key.

        Codes worth branching on: ``refund.nothing_to_refund``, ``refund.exceeds_refundable``,
        ``refund.no_address`` (the payer address is not refundable - ask for one),
        ``refund.dust`` (below the network's minimum), ``refund.reference_collision``,
        ``payout.insufficient_funds`` (retryable), ``merchant.wrong_key_kind``.
        """
        return cast(Payout, await self._call("POST /v1/payment/refund", params, **options))

    async def resolve(self, params: PaymentResolveBody, **options: Any) -> Resolution:
        """``POST /v1/payment/resolve`` - settle an underpaid (``wrong_amount``) invoice.

        Codes worth branching on: ``payment.not_found``, ``payment.bad_status`` (not
        ``wrong_amount``), ``refund.nothing_to_refund``, ``refund.no_address``,
        ``refund.exceeds_excess``.
        """
        return cast(Resolution, await self._call("POST /v1/payment/resolve", params, **options))

    async def batch(self, params: RefundBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/refund/batch`` - up to 5000 refunds; track with ``batches.info``.

        Codes worth branching on: ``payout.batch_too_large``, ``payout.empty_batch``,
        ``refund.reference_collision``, ``request.missing_field`` (an item without ``reference``),
        ``merchant.wrong_key_kind``, ``idempotency.key_reused``.
        """
        return cast(BatchSubmitted, await self._call("POST /v1/refund/batch", params, **options))
