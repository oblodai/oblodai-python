"""Balances, account-level facts, and the public reference catalog."""

from __future__ import annotations

from typing import Any, Optional, cast

from ..contract.models import Balance, Currencies, ExchangeRate, ReferralInfo, VrcsStatus
from ..contract.requests import ExchangeRateListBody
from ..core.pagination import Page
from .base import Resource

__all__ = ["Account", "Catalog"]


class Account(Resource):
    """Balances and account-level facts."""

    def balance(self, **options: Any) -> Balance:
        """``POST /v1/balance`` - available balance per currency."""
        return cast(Balance, self._call("POST /v1/balance", **options))

    def referral(self, **options: Any) -> ReferralInfo:
        """``POST /v1/referral/info`` - referral code, link and earnings."""
        return cast(ReferralInfo, self._call("POST /v1/referral/info", **options))

    def vrcs(self, enabled: Optional[bool] = None, **options: Any) -> VrcsStatus:
        """``POST /v1/vrcs`` - read (no argument) or set volatility-risk conversion.

        When enabled, volatile deposits are auto-converted to USDT.
        """
        return cast(
            VrcsStatus,
            self._call(
                "POST /v1/vrcs", None if enabled is None else {"enabled": enabled}, **options
            ),
        )


class Catalog(Resource):
    """Public reference data - no credentials needed."""

    def currencies(self, **options: Any) -> Currencies:
        """``GET /v1/currencies`` - every asset, its networks and live availability."""
        return cast(Currencies, self._call("GET /v1/currencies", **options))

    def exchange_rates(
        self, params: Optional[ExchangeRateListBody] = None, **options: Any
    ) -> Page[ExchangeRate]:
        """``POST /v1/exchange-rate/list`` - current rates, optionally filtered."""
        return self._page("POST /v1/exchange-rate/list", params, **options)
