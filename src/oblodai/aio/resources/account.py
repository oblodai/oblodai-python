"""Balances, account-level facts, and the public reference catalog."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/account.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, Optional, cast

from ...contract.models import Balance, Currencies, ExchangeRate, ReferralInfo, VrcsStatus
from ...contract.requests import ExchangeRateListBody
from ...core.pagination import AsyncPage
from ..base import AsyncResource

__all__ = ["AsyncAccount", "AsyncCatalog"]


class AsyncAccount(AsyncResource):
    """Balances and account-level facts."""

    async def balance(self, **options: Any) -> Balance:
        """``POST /v1/balance`` - available balance per currency."""
        return cast(Balance, await self._call("POST /v1/balance", **options))

    async def referral(self, **options: Any) -> ReferralInfo:
        """``POST /v1/referral/info`` - referral code, link and earnings."""
        return cast(ReferralInfo, await self._call("POST /v1/referral/info", **options))

    async def vrcs(self, enabled: Optional[bool] = None, **options: Any) -> VrcsStatus:
        """``POST /v1/vrcs`` - read (no argument) or set volatility-risk conversion.

        When enabled, volatile deposits are auto-converted to USDT.
        """
        return cast(
            VrcsStatus,
            await self._call(
                "POST /v1/vrcs", None if enabled is None else {"enabled": enabled}, **options
            ),
        )


class AsyncCatalog(AsyncResource):
    """Public reference data - no credentials needed."""

    async def currencies(self, **options: Any) -> Currencies:
        """``GET /v1/currencies`` - every asset, its networks and live availability."""
        return cast(Currencies, await self._call("GET /v1/currencies", **options))

    def exchange_rates(
        self, params: Optional[ExchangeRateListBody] = None, **options: Any
    ) -> AsyncPage[ExchangeRate]:
        """``POST /v1/exchange-rate/list`` - current rates, optionally filtered."""
        return self._page("POST /v1/exchange-rate/list", params, **options)
