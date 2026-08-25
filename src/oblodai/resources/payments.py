"""Invoices: create, look up, cancel, list, and the payer-facing checkout endpoints."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union, cast

from ..contract.models import (
    BatchSubmitted,
    EmailSent,
    OkResult,
    Payment,
    PublicPayment,
    QrCode,
    ServiceMethod,
)
from ..contract.requests import (
    PayIdSelectBody,
    PaymentBatchBody,
    PaymentBody,
    PaymentHistoryBody,
    PaymentSendEmailBody,
    PaymentServicesBody,
)
from ..core.pagination import Page
from .base import Resource

__all__ = ["PaymentLookup", "Payments"]

#: Identify an invoice by its ``uuid`` or by your ``order_id`` - a bare string is the uuid.
PaymentLookup = Union[str, Mapping[str, str]]


class Payments(Resource):
    """Invoices. Payment key."""

    def create(self, params: PaymentBody, **options: Any) -> Payment:
        """``POST /v1/payment`` - create an invoice.

        Idempotent by ``order_id`` and by ``Idempotency-Key``.
        """
        return cast(Payment, self._call("POST /v1/payment", params, **options))

    def info(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """``POST /v1/payment/info`` - by ``uuid`` or ``order_id``.

        Includes ``refunds`` and ``refund_status``.
        """
        return cast(Payment, self._call("POST /v1/payment/info", by_uuid(lookup), **options))

    def get(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """Alias of :meth:`info`."""
        return cast(Payment, self._call("POST /v1/payment/info", by_uuid(lookup), **options))

    def cancel(self, lookup: PaymentLookup, **options: Any) -> Payment:
        """``POST /v1/payment/cancel`` - cancel an unpaid invoice.

        409 ``invoice.not_payable`` once a deposit was seen.
        """
        return cast(Payment, self._call("POST /v1/payment/cancel", by_uuid(lookup), **options))

    def history(self, params: Optional[PaymentHistoryBody] = None, **options: Any) -> Page[Payment]:
        """``POST /v1/payment/history`` - newest first.

        ``.first()`` gives one page, iterating the result walks every page.
        """
        return self._page("POST /v1/payment/history", params, **options)

    def list(self, params: Optional[PaymentHistoryBody] = None, **options: Any) -> Page[Payment]:
        """Alias of :meth:`history`."""
        return self._page("POST /v1/payment/history", params, **options)

    def batch(self, params: PaymentBatchBody, **options: Any) -> BatchSubmitted:
        """``POST /v1/payment/batch`` - up to 5000 invoices asynchronously; track with ``batches.info``."""
        return cast(BatchSubmitted, self._call("POST /v1/payment/batch", params, **options))

    def qr(self, lookup: PaymentLookup, **options: Any) -> QrCode:
        """``POST /v1/payment/qr`` - QR image of the invoice's payment URI."""
        return cast(QrCode, self._call("POST /v1/payment/qr", by_uuid(lookup), **options))

    def services(
        self, params: Optional[PaymentServicesBody] = None, **options: Any
    ) -> Page[ServiceMethod]:
        """``POST /v1/payment/services`` - currencies/networks accepted for deposits."""
        return self._page("POST /v1/payment/services", params, **options)

    def send_email(self, params: PaymentSendEmailBody, **options: Any) -> EmailSent:
        """``POST /v1/payment/send-email`` - email the receipt (defaults to ``payer_email``)."""
        return cast(EmailSent, self._call("POST /v1/payment/send-email", params, **options))

    def resend(self, lookup: PaymentLookup, **options: Any) -> OkResult:
        """``POST /v1/payment/resend`` - re-deliver the invoice's last webhook."""
        return cast(OkResult, self._call("POST /v1/payment/resend", by_uuid(lookup), **options))

    # --- payer-facing (public, unsigned) - for custom checkout pages ---

    def public_view(self, uuid: str, **options: Any) -> PublicPayment:
        """``GET /v1/pay/{id}`` - the invoice as the payer sees it. No credentials needed."""
        return cast(
            PublicPayment,
            self._call("GET /v1/pay/{id}", path_params={"id": uuid}, **options),
        )

    def select(self, uuid: str, params: PayIdSelectBody, **options: Any) -> PublicPayment:
        """``POST /v1/pay/{id}/select`` - pick the asset/network on a multi-currency invoice."""
        return cast(
            PublicPayment,
            self._call("POST /v1/pay/{id}/select", params, path_params={"id": uuid}, **options),
        )

    def public_qr(self, uuid: str, **options: Any) -> QrCode:
        """``GET /v1/pay/{id}/qr`` - QR for the payer page. No credentials needed."""
        return cast(QrCode, self._call("GET /v1/pay/{id}/qr", path_params={"id": uuid}, **options))


def by_uuid(ref: PaymentLookup) -> Dict[str, str]:
    """A bare string is taken as the ``uuid``."""
    return {"uuid": ref} if isinstance(ref, str) else dict(ref)
