"""Merchant-level configuration exposed over the API."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/settings.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, List, Optional, cast

from ...contract.models import (
    AcceptedMethod,
    AccuracyConfig,
    ApiAllowlist,
    AutoRefundConfig,
    AutoWithdrawRule,
    DiscountRule,
    OkResult,
    PaymentFeeConfig,
)
from ...contract.requests import (
    AutoWithdrawSetBody,
    PaymentAcceptedListBody,
    PaymentAcceptedSetBody,
    PaymentAccuracySetBody,
    PaymentAutorefundSetBody,
    PaymentDiscountListBody,
    PaymentDiscountSetBody,
    PaymentFeeConfigSetBody,
)
from ...core.pagination import AsyncPage
from ..base import AsyncResource

__all__ = ["AsyncSettings"]


class AsyncSettings(AsyncResource):
    """Discounts, accuracy, auto-refunds, accepted methods, fee split, sweeps and the IP list."""

    async def set_discount(self, params: PaymentDiscountSetBody, **options: Any) -> DiscountRule:
        """``POST /v1/payment/discount/set`` - payer-facing discount/markup per currency+network."""
        return cast(
            DiscountRule, await self._call("POST /v1/payment/discount/set", params, **options)
        )

    def list_discounts(
        self, params: Optional[PaymentDiscountListBody] = None, **options: Any
    ) -> AsyncPage[DiscountRule]:
        """``POST /v1/payment/discount/list``."""
        return self._page("POST /v1/payment/discount/list", params, **options)

    async def get_accuracy(self, **options: Any) -> AccuracyConfig:
        """``POST /v1/payment/accuracy/get`` - under/overpayment tolerance."""
        return cast(AccuracyConfig, await self._call("POST /v1/payment/accuracy/get", **options))

    async def set_accuracy(self, params: PaymentAccuracySetBody, **options: Any) -> AccuracyConfig:
        """``POST /v1/payment/accuracy/set``."""
        return cast(
            AccuracyConfig, await self._call("POST /v1/payment/accuracy/set", params, **options)
        )

    async def get_auto_refund(self, **options: Any) -> AutoRefundConfig:
        """``POST /v1/payment/autorefund/get``."""
        return cast(
            AutoRefundConfig, await self._call("POST /v1/payment/autorefund/get", **options)
        )

    async def set_auto_refund(
        self, params: PaymentAutorefundSetBody, **options: Any
    ) -> AutoRefundConfig:
        """``POST /v1/payment/autorefund/set`` - refund over/underpayments automatically."""
        return cast(
            AutoRefundConfig, await self._call("POST /v1/payment/autorefund/set", params, **options)
        )

    def list_accepted(
        self, params: Optional[PaymentAcceptedListBody] = None, **options: Any
    ) -> AsyncPage[AcceptedMethod]:
        """``POST /v1/payment/accepted/list`` - which currency/network pairs invoices may use."""
        return self._page("POST /v1/payment/accepted/list", params, **options)

    async def set_accepted(self, params: PaymentAcceptedSetBody, **options: Any) -> OkResult:
        """``POST /v1/payment/accepted/set``."""
        return cast(OkResult, await self._call("POST /v1/payment/accepted/set", params, **options))

    async def get_payment_fee_config(self, **options: Any) -> PaymentFeeConfig:
        """``POST /v1/payment/fee-config/get`` - share of the network fee charged to the payer."""
        return cast(
            PaymentFeeConfig, await self._call("POST /v1/payment/fee-config/get", **options)
        )

    async def set_payment_fee_config(
        self, params: PaymentFeeConfigSetBody, **options: Any
    ) -> PaymentFeeConfig:
        """``POST /v1/payment/fee-config/set``."""
        return cast(
            PaymentFeeConfig, await self._call("POST /v1/payment/fee-config/set", params, **options)
        )

    async def list_auto_withdraw(self, **options: Any) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/list``. Payout key."""
        return cast(
            List[AutoWithdrawRule], await self._plain_list("POST /v1/auto-withdraw/list", **options)
        )

    async def set_auto_withdraw(
        self, params: AutoWithdrawSetBody, **options: Any
    ) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/set`` - sweep a currency once the balance passes ``min_amount``."""
        return cast(
            List[AutoWithdrawRule],
            await self._plain_list("POST /v1/auto-withdraw/set", params, **options),
        )

    async def delete_auto_withdraw(self, currency: str, **options: Any) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/delete``."""
        return cast(
            List[AutoWithdrawRule],
            await self._plain_list(
                "POST /v1/auto-withdraw/delete", {"currency": currency}, **options
            ),
        )

    async def list_api_allowlist(self, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/list`` - source IPs allowed to use the API keys. Payout key."""
        return cast(ApiAllowlist, await self._call("POST /v1/api-allowlist/list", **options))

    async def add_api_allowlist(self, cidr: str, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/add``."""
        return cast(
            ApiAllowlist, await self._call("POST /v1/api-allowlist/add", {"cidr": cidr}, **options)
        )

    async def remove_api_allowlist(self, cidr: str, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/remove``."""
        return cast(
            ApiAllowlist,
            await self._call("POST /v1/api-allowlist/remove", {"cidr": cidr}, **options),
        )

    async def enable_api_allowlist(self, enabled: bool, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/enable`` - switch enforcement on or off (the list is kept)."""
        return cast(
            ApiAllowlist,
            await self._call("POST /v1/api-allowlist/enable", {"enabled": enabled}, **options),
        )
