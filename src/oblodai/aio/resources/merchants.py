"""Merchant provisioning - for platforms that onboard merchants themselves.

These routes are not HMAC-signed; a self-hosted gateway gates them with its admin token
(the ``admin_token`` client option).
"""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/merchants.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, cast

from ...contract.models import MerchantOnboarded, SandboxStore
from ...contract.requests import MerchantsBody
from ..base import AsyncResource

__all__ = ["AsyncMerchants"]


class AsyncMerchants(AsyncResource):
    """Create merchants and mint their keys."""

    async def create(self, params: MerchantsBody, **options: Any) -> MerchantOnboarded:
        """``POST /v1/merchants`` - create a merchant and mint its keys (shown once)."""
        return cast(MerchantOnboarded, await self._call("POST /v1/merchants", params, **options))

    async def create_sandbox(self, merchant_id: str, **options: Any) -> SandboxStore:
        """``POST /v1/merchants/{id}/sandbox`` - the merchant's dev store and its ``test_`` key.

        Idempotent: calling it again returns the existing store with ``created: false``.
        """
        return cast(
            SandboxStore,
            await self._call(
                "POST /v1/merchants/{id}/sandbox", path_params={"id": merchant_id}, **options
            ),
        )
