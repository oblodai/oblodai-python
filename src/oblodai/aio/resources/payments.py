"""Invoices: create, look up, cancel, list, and the payer-facing checkout endpoints."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/payments.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union, cast

from ...contract.models import (
    BatchSubmitted,
    EmailSent,
    OkResult,
    Payment,
    PublicPayment,
    QrCode,
    ServiceMethod,
)
from ...contract.requests import (
    PayIdSelectBody,
    PaymentBatchBody,
    PaymentBody,
    PaymentHistoryBody,
    PaymentSendEmailBody,
    PaymentServicesBody,
)
from ...core.pagination import AsyncPage
from ..base import AsyncResource

__all__ = ["AsyncPayments", "PaymentLookup"]

#: Identify an invoice by its ``uuid`` or by your ``order_id`` - a bare string is the uuid.
PaymentLookup = Union[str, Mapping[str, str]]


class AsyncPayments(AsyncResource):
    """Invoices. Payment key."""

    async def create(self, params: PaymentBody, **options: Any) -> Payment:
        """``POST /v1/payment`` - create an invoice.

        Idempotent by ``order_id`` and by ``Idempotency-Key``.

        Codes worth branching on: ``payment.bad_amount``, ``payment.below_minimum``,
        ``payment.minimum_unavailable`` (the rate feed is down - retryable),
        ``payment.unsupported_network``, ``payment.network_required`` (a multi-network asset with
        no ``network``), ``request.unknown_currency``, ``idempotency.key_reused`` (the same key
        with a different body).
        """
        return cast(Payment, await self._call("POST /v1/payment", params, **options))

    async def info(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """``POST /v1/payment/info`` - by ``uuid`` or ``order_id``.

        Includes ``refunds`` and ``refund_status``.
        """
        return cast(Payment, await self._call("POST /v1/payment/info", by_uuid(lookup), **options))

    async def get(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """Alias of :meth:`info`."""
        return cast(Payment, await self._call("POST /v1/payment/info", by_uuid(lookup), **options))

    async def cancel(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """``POST /v1/payment/cancel`` - cancel an unpaid invoice.

        409 ``invoice.not_payable`` once a deposit was seen.
        """
        return cast(
            Payment, await self._call("POST /v1/payment/cancel", by_uuid(lookup), **options)
        )

    def history(
        self, params: Optional[PaymentHistoryBody] = None, **options: Any
    ) -> AsyncPage[Payment]:
        """``POST /v1/payment/history`` - newest first.

        ``await .first()`` gives one page, ``async for`` walks every page.
        """
        return self._page("POST /v1/payment/history", params, **options)

    def list(
        self, params: Optional[PaymentHistoryBody] = None, **options: Any
    ) -> AsyncPage[Payment]:
        """Alias of :meth:`history`."""
        return self._page("POST /v1/payment/history", params, **options)

    async def batch(self, params: PaymentBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/payment/batch`` - up to 5000 invoices asynchronously; track with ``batches.info``.

        Codes worth branching on: ``payment.bad_amount``, ``payment.below_minimum``,
        ``request.unknown_currency``, ``request.missing_field`` (an item without ``order_id``),
        ``payout.batch_too_large``, ``payout.empty_batch``, ``idempotency.key_reused``.
        """
        return cast(BatchSubmitted, await self._call("POST /v1/payment/batch", params, **options))

    async def qr(self, lookup: PaymentLookup, **options: Any) -> QrCode:
        """``POST /v1/payment/qr`` - QR image of the invoice's payment URI."""
        return cast(QrCode, await self._call("POST /v1/payment/qr", by_uuid(lookup), **options))

    def services(
        self, params: Optional[PaymentServicesBody] = None, **options: Any
    ) -> AsyncPage[ServiceMethod]:
        """``POST /v1/payment/services`` - currencies/networks accepted for deposits."""
        return self._page("POST /v1/payment/services", params, **options)

    async def send_email(self, params: PaymentSendEmailBody, **options: Any) -> EmailSent:
        """``POST /v1/payment/send-email`` - email the receipt (defaults to ``payer_email``)."""
        return cast(EmailSent, await self._call("POST /v1/payment/send-email", params, **options))

    async def resend(self, lookup: PaymentLookup, **options: Any) -> OkResult:
        """``POST /v1/payment/resend`` - re-deliver the invoice's last webhook."""
        return cast(
            OkResult, await self._call("POST /v1/payment/resend", by_uuid(lookup), **options)
        )

    # --- payer-facing (public, unsigned) - for custom checkout pages ---

    async def public_view(self, uuid: str, **options: Any) -> PublicPayment:
        """``GET /v1/pay/{id}`` - the invoice as the payer sees it. No credentials needed."""
        return cast(
            PublicPayment,
            await self._call("GET /v1/pay/{id}", path_params={"id": uuid}, **options),
        )

    async def select(self, uuid: str, params: PayIdSelectBody, **options: Any) -> PublicPayment:
        """``POST /v1/pay/{id}/select`` - pick the asset/network on a multi-currency invoice."""
        return cast(
            PublicPayment,
            await self._call(
                "POST /v1/pay/{id}/select", params, path_params={"id": uuid}, **options
            ),
        )

    async def public_qr(self, uuid: str, **options: Any) -> QrCode:
        """``GET /v1/pay/{id}/qr`` - QR for the payer page. No credentials needed."""
        return cast(
            QrCode, await self._call("GET /v1/pay/{id}/qr", path_params={"id": uuid}, **options)
        )


def by_uuid(ref: PaymentLookup) -> Dict[str, str]:
    """A bare string is taken as the ``uuid``."""
    return {"uuid": ref} if isinstance(ref, str) else dict(ref)
