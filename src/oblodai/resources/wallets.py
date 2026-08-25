"""Static deposit wallets: one permanent address per customer, deposits reported as ``wallet.paid``."""

from __future__ import annotations

from typing import Any, cast

from ..contract.models import Payout, Wallet, WalletBlocked, WalletQr
from ..contract.requests import WalletBlockBody, WalletBlockedAddressRefundBody, WalletBody
from .base import Resource

__all__ = ["Wallets"]


class Wallets(Resource):
    """Static wallets. Payment key, except the blocked-deposit refund (payout key)."""

    def create(self, params: WalletBody, **options: Any) -> Wallet:
        """``POST /v1/wallet`` - idempotent by ``order_id``."""
        return cast(Wallet, self._call("POST /v1/wallet", params, **options))

    def qr(self, address: str, **options: Any) -> WalletQr:
        """``POST /v1/wallet/qr``."""
        return cast(WalletQr, self._call("POST /v1/wallet/qr", {"address": address}, **options))

    def block(self, params: WalletBlockBody, **options: Any) -> WalletBlocked:
        """``POST /v1/wallet/block`` - stop crediting an address.

        Later deposits wait for a refund decision.
        """
        return cast(WalletBlocked, self._call("POST /v1/wallet/block", params, **options))

    def refund_blocked_deposit(
        self, params: WalletBlockedAddressRefundBody, **options: Any
    ) -> Payout:
        """``POST /v1/wallet/blocked-address-refund`` - send funds off a blocked address back."""
        return cast(Payout, self._call("POST /v1/wallet/blocked-address-refund", params, **options))
