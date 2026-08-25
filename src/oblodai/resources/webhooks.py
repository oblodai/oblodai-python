"""Webhook endpoint management and delivery inspection.

Verification of an incoming delivery lives in :mod:`oblodai.webhooks` and needs no client.
"""

from __future__ import annotations

from typing import Any, Optional, cast

from ..contract.models import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookSecretRotated,
    WebhookTestResult,
)
from ..contract.requests import (
    PaymentTestingWebhookBody,
    TestWebhookPaymentBody,
    WebhooksDeliveriesBody,
)
from ..core.pagination import Page
from .base import Resource

__all__ = ["Webhooks"]


class Webhooks(Resource):
    """Endpoint registration, secret rotation and the delivery log."""

    def register(self, url: str, **options: Any) -> WebhookEndpoint:
        """``POST /v1/webhooks`` - register (or replace) the endpoint; returns the secret once."""
        return cast(WebhookEndpoint, self._call("POST /v1/webhooks", {"url": url}, **options))

    def rotate_secret(self, **options: Any) -> WebhookSecretRotated:
        """``POST /v1/webhooks/rotate-secret`` - new secret; the old one keeps verifying.

        Until ``previous_secret_valid_until``. Payout key.
        """
        return cast(WebhookSecretRotated, self._call("POST /v1/webhooks/rotate-secret", **options))

    def deliveries(
        self, params: Optional[WebhooksDeliveriesBody] = None, **options: Any
    ) -> Page[WebhookDelivery]:
        """``POST /v1/webhooks/deliveries`` - delivery log, newest first."""
        return self._page("POST /v1/webhooks/deliveries", params, **options)

    def test(self, kind: str, params: TestWebhookPaymentBody, **options: Any) -> WebhookTestResult:
        """``POST /v1/test-webhook/{payment|payout|wallet}``.

        Delivers a sample event of that kind to ``url_callback``, signed like a real one.
        """
        if kind not in ("payment", "payout", "wallet"):
            raise ValueError(f'unknown webhook kind "{kind}"; use payment, payout or wallet')
        return cast(
            WebhookTestResult, self._call(f"POST /v1/test-webhook/{kind}", params, **options)
        )

    def test_legacy(self, params: PaymentTestingWebhookBody, **options: Any) -> WebhookTestResult:
        """``POST /v1/payment/testing-webhook`` - the older rehearsal door (payment events only).

        .. deprecated:: 1.3.0 use :meth:`test` with ``"payment"``.
        """
        return cast(
            WebhookTestResult, self._call("POST /v1/payment/testing-webhook", params, **options)
        )
