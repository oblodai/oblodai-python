"""Synchronous resource namespaces, one per area of the API."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/__init__.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from ..base import AsyncResource, FileResult
from .account import AsyncAccount, AsyncCatalog
from .batches import AsyncBatches, AsyncTransfers
from .documents import AsyncDocuments
from .links import AsyncPaymentLinks, AsyncPayoutLinks
from .merchants import AsyncMerchants
from .payments import AsyncPayments
from .payouts import AsyncPayouts
from .refunds import AsyncRefunds
from .sandbox import AsyncSandbox
from .settings import AsyncSettings
from .splits import AsyncSplits
from .wallets import AsyncWallets
from .webhooks import AsyncWebhooks

__all__ = [
    "AsyncAccount",
    "AsyncBatches",
    "AsyncCatalog",
    "AsyncDocuments",
    "AsyncMerchants",
    "AsyncPaymentLinks",
    "AsyncPayments",
    "AsyncPayoutLinks",
    "AsyncPayouts",
    "AsyncRefunds",
    "AsyncResource",
    "AsyncSandbox",
    "AsyncSettings",
    "AsyncSplits",
    "AsyncTransfers",
    "AsyncWallets",
    "AsyncWebhooks",
    "FileResult",
]
