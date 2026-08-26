"""Merchant-level configuration exposed over the API."""

from __future__ import annotations

from typing import Any, List, Optional, cast

from ..contract.models import (
    AcceptedMethod,
    AccuracyConfig,
    ApiAllowlist,
    AutoRefundConfig,
    AutoWithdrawRule,
    DiscountRule,
    OkResult,
    PaymentFeeConfig,
)
from ..contract.requests import (
    AutoWithdrawSetBody,
    PaymentAcceptedListBody,
    PaymentAcceptedSetBody,
    PaymentAccuracySetBody,
    PaymentAutorefundSetBody,
    PaymentDiscountListBody,
    PaymentDiscountSetBody,
    PaymentFeeConfigSetBody,
)
from ..core.pagination import Page
from .base import Resource

__all__ = ["Settings"]


class Settings(Resource):
    """Discounts, accuracy, auto-refunds, accepted methods, fee split, sweeps and the IP list."""

    def set_discount(self, params: PaymentDiscountSetBody, **options: Any) -> DiscountRule:
        """``POST /v1/payment/discount/set`` - payer-facing discount/markup per currency+network."""
        return cast(DiscountRule, self._call("POST /v1/payment/discount/set", params, **options))

    def list_discounts(
        self, params: Optional[PaymentDiscountListBody] = None, **options: Any
    ) -> Page[DiscountRule]:
        """``POST /v1/payment/discount/list``."""
        return self._page("POST /v1/payment/discount/list", params, **options)

    def get_accuracy(self, **options: Any) -> AccuracyConfig:
        """``POST /v1/payment/accuracy/get`` - under/overpayment tolerance."""
        return cast(AccuracyConfig, self._call("POST /v1/payment/accuracy/get", **options))

    def set_accuracy(self, params: PaymentAccuracySetBody, **options: Any) -> AccuracyConfig:
        """``POST /v1/payment/accuracy/set``."""
        return cast(AccuracyConfig, self._call("POST /v1/payment/accuracy/set", params, **options))

    def get_auto_refund(self, **options: Any) -> AutoRefundConfig:
        """``POST /v1/payment/autorefund/get``."""
        return cast(AutoRefundConfig, self._call("POST /v1/payment/autorefund/get", **options))

    def set_auto_refund(self, params: PaymentAutorefundSetBody, **options: Any) -> AutoRefundConfig:
        """``POST /v1/payment/autorefund/set`` - refund over/underpayments automatically."""
        return cast(
            AutoRefundConfig, self._call("POST /v1/payment/autorefund/set", params, **options)
        )

    def list_accepted(
        self, params: Optional[PaymentAcceptedListBody] = None, **options: Any
    ) -> Page[AcceptedMethod]:
        """``POST /v1/payment/accepted/list`` - which currency/network pairs invoices may use."""
        return self._page("POST /v1/payment/accepted/list", params, **options)

    def set_accepted(self, params: PaymentAcceptedSetBody, **options: Any) -> OkResult:
        """``POST /v1/payment/accepted/set``."""
        return cast(OkResult, self._call("POST /v1/payment/accepted/set", params, **options))

    def get_payment_fee_config(self, **options: Any) -> PaymentFeeConfig:
        """``POST /v1/payment/fee-config/get`` - share of the network fee charged to the payer."""
        return cast(PaymentFeeConfig, self._call("POST /v1/payment/fee-config/get", **options))

    def set_payment_fee_config(
        self, params: PaymentFeeConfigSetBody, **options: Any
    ) -> PaymentFeeConfig:
        """``POST /v1/payment/fee-config/set``."""
        return cast(
            PaymentFeeConfig, self._call("POST /v1/payment/fee-config/set", params, **options)
        )

    def list_auto_withdraw(self, **options: Any) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/list``."""
        return cast(
            List[AutoWithdrawRule], self._plain_list("POST /v1/auto-withdraw/list", **options)
        )

    def set_auto_withdraw(
        self, params: AutoWithdrawSetBody, **options: Any
    ) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/set`` - sweep a currency once the balance passes ``min_amount``."""
        return cast(
            List[AutoWithdrawRule],
            self._plain_list("POST /v1/auto-withdraw/set", params, **options),
        )

    def delete_auto_withdraw(self, currency: str, **options: Any) -> List[AutoWithdrawRule]:
        """``POST /v1/auto-withdraw/delete``."""
        return cast(
            List[AutoWithdrawRule],
            self._plain_list("POST /v1/auto-withdraw/delete", {"currency": currency}, **options),
        )

    def list_api_allowlist(self, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/list`` - source IPs allowed to use the API key."""
        return cast(ApiAllowlist, self._call("POST /v1/api-allowlist/list", **options))

    def add_api_allowlist(self, cidr: str, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/add``."""
        return cast(
            ApiAllowlist, self._call("POST /v1/api-allowlist/add", {"cidr": cidr}, **options)
        )

    def remove_api_allowlist(self, cidr: str, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/remove``."""
        return cast(
            ApiAllowlist, self._call("POST /v1/api-allowlist/remove", {"cidr": cidr}, **options)
        )

    def enable_api_allowlist(self, enabled: bool, **options: Any) -> ApiAllowlist:
        """``POST /v1/api-allowlist/enable`` - switch enforcement on or off (the list is kept)."""
        return cast(
            ApiAllowlist,
            self._call("POST /v1/api-allowlist/enable", {"enabled": enabled}, **options),
        )
