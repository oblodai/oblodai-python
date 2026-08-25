"""Synchronous resource namespaces, one per area of the API."""

from __future__ import annotations

from .account import Account, Catalog
from .base import FileResult, Resource
from .batches import Batches, Transfers
from .documents import Documents
from .links import PaymentLinks, PayoutLinks
from .merchants import Merchants
from .payments import Payments
from .payouts import Payouts
from .refunds import Refunds
from .sandbox import Sandbox
from .settings import Settings
from .splits import Splits
from .wallets import Wallets
from .webhooks import Webhooks

__all__ = [
    "Account",
    "Batches",
    "Catalog",
    "Documents",
    "FileResult",
    "Merchants",
    "PaymentLinks",
    "Payments",
    "PayoutLinks",
    "Payouts",
    "Refunds",
    "Resource",
    "Sandbox",
    "Settings",
    "Splits",
    "Transfers",
    "Wallets",
    "Webhooks",
]
