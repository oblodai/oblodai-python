"""Payout links (cheques) and reusable payment links."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union, cast

from ..contract.models import (
    BatchElement,
    ClaimPreview,
    ClaimResult,
    PaymentLink,
    PaymentLinkCreated,
    PaymentLinkToggled,
    PayoutLink,
    PublicPayment,
    PublicPaymentLink,
)
from ..contract.requests import (
    ClaimTokenBody,
    LinkIdCheckoutBody,
    PaymentLinkBody,
    PaymentLinkInfoBody,
    PaymentLinkListBody,
    PayoutLinkBatchBody,
    PayoutLinkBody,
    PayoutLinkChequeBody,
    PayoutLinkListBody,
)
from ..core.pagination import Page
from .base import FileResult, Resource

__all__ = ["LinkRef", "PaymentLinks", "PayoutLinks"]

#: A link id as a bare string, or a mapping carrying ``link_id``.
LinkRef = Union[str, Mapping[str, str]]


class PayoutLinks(Resource):
    """Cheques: funds reserved now, claimed later by whoever holds the token. Payout key."""

    def create(self, params: PayoutLinkBody, **options: Any) -> PayoutLink:
        """``POST /v1/payout/link`` - reserve funds and mint a claim token.

        ``claim_token``/``claim_url`` are returned once. Idempotent by ``reference``.
        """
        return cast(PayoutLink, self._call("POST /v1/payout/link", params, **options))

    def info(self, link: LinkRef, **options: Any) -> PayoutLink:
        """``POST /v1/payout/link/info``."""
        return cast(
            PayoutLink,
            self._call("POST /v1/payout/link/info", {"link_id": link_id_of(link)}, **options),
        )

    def get(self, link: LinkRef, **options: Any) -> PayoutLink:
        """Alias of :meth:`info`."""
        return cast(
            PayoutLink,
            self._call("POST /v1/payout/link/info", {"link_id": link_id_of(link)}, **options),
        )

    def list(self, params: Optional[PayoutLinkListBody] = None, **options: Any) -> Page[PayoutLink]:
        """``POST /v1/payout/link/list``."""
        return self._page("POST /v1/payout/link/list", params, **options)

    def cancel(self, link: LinkRef, **options: Any) -> PayoutLink:
        """``POST /v1/payout/link/cancel`` - release the reserved funds of an unclaimed link."""
        return cast(
            PayoutLink,
            self._call("POST /v1/payout/link/cancel", {"link_id": link_id_of(link)}, **options),
        )

    def batch(self, params: PayoutLinkBatchBody, **options: Any) -> Dict[str, List[BatchElement]]:
        """``POST /v1/payout/link/batch`` - SYNCHRONOUS: many links in one signed call.

        ``reference`` is required on every item; each element reports its own outcome.
        """
        return cast(
            Dict[str, List[BatchElement]],
            self._call("POST /v1/payout/link/batch", params, **options),
        )

    def cheque(self, params: PayoutLinkChequeBody, **options: Any) -> FileResult:
        """``POST /v1/payout/link/cheque`` - printable PDF cheque for a claim token."""
        return self._file("POST /v1/payout/link/cheque", body=params, **options)

    # --- recipient side (public, unsigned) ---

    def claim_preview(self, token: str, **options: Any) -> ClaimPreview:
        """``GET /v1/claim/{token}`` - what the recipient sees before claiming."""
        return cast(
            ClaimPreview,
            self._call("GET /v1/claim/{token}", path_params={"token": token}, **options),
        )

    def claim(self, token: str, params: ClaimTokenBody, **options: Any) -> ClaimResult:
        """``POST /v1/claim/{token}`` - claim to an address (and passcode when the link has one)."""
        return cast(
            ClaimResult,
            self._call("POST /v1/claim/{token}", params, path_params={"token": token}, **options),
        )


class PaymentLinks(Resource):
    """Reusable payment links (tip jars, price tags): each checkout spawns an invoice."""

    def create(self, params: PaymentLinkBody, **options: Any) -> PaymentLinkCreated:
        """``POST /v1/payment/link``."""
        return cast(PaymentLinkCreated, self._call("POST /v1/payment/link", params, **options))

    def info(
        self, link: LinkRef, page: Optional[PaymentLinkInfoBody] = None, **options: Any
    ) -> PaymentLink:
        """``POST /v1/payment/link/info`` - the link plus a page of its invoices (``payments``)."""
        body: Dict[str, Any] = {"link_id": link_id_of(link)}
        body.update(page or {})
        return cast(PaymentLink, self._call("POST /v1/payment/link/info", body, **options))

    def get(
        self, link: LinkRef, page: Optional[PaymentLinkInfoBody] = None, **options: Any
    ) -> PaymentLink:
        """Alias of :meth:`info`."""
        body: Dict[str, Any] = {"link_id": link_id_of(link)}
        body.update(page or {})
        return cast(PaymentLink, self._call("POST /v1/payment/link/info", body, **options))

    def list(
        self, params: Optional[PaymentLinkListBody] = None, **options: Any
    ) -> Page[PaymentLink]:
        """``POST /v1/payment/link/list``."""
        return self._page("POST /v1/payment/link/list", params, **options)

    def toggle(self, link: LinkRef, active: bool, **options: Any) -> PaymentLinkToggled:
        """``POST /v1/payment/link/toggle`` - enable or disable a link."""
        return cast(
            PaymentLinkToggled,
            self._call(
                "POST /v1/payment/link/toggle",
                {"link_id": link_id_of(link), "active": active},
                **options,
            ),
        )

    # --- payer side (public, unsigned) ---

    def public_view(self, link_id: str, **options: Any) -> PublicPaymentLink:
        """``GET /v1/link/{id}`` - the link as the payer sees it. No credentials needed."""
        return cast(
            PublicPaymentLink,
            self._call("GET /v1/link/{id}", path_params={"id": link_id}, **options),
        )

    def checkout(
        self, link_id: str, params: Optional[LinkIdCheckoutBody] = None, **options: Any
    ) -> PublicPayment:
        """``POST /v1/link/{id}/checkout`` - spawn an invoice from the link (rate-capped per IP)."""
        return cast(
            PublicPayment,
            self._call(
                "POST /v1/link/{id}/checkout",
                params or {},
                path_params={"id": link_id},
                **options,
            ),
        )


def link_id_of(ref: LinkRef) -> str:
    """The ``link_id`` of a link given as a string or a mapping."""
    return ref if isinstance(ref, str) else ref["link_id"]
