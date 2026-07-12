"""Асинхронные ресурсы. Зеркало sync_resources с await; хелперы переиспользуются."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._http import AsyncHTTPClient
from ..models import (
    Currency,
    AutoWithdrawRule,
    Balance,
    Delivery,
    ExchangeRate,
    MassPayoutResult,
    Payment,
    PaymentList,
    Payout,
    PayoutCalculation,
    PayoutList,
    ReferralInfo,
    ServiceMethod,
    Wallet,
    WebhookRegistration,
)
from .sync_resources import _clean, _lookup


class _Base:
    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http


class Payments(_Base):
    async def create(self, **params: Any) -> Payment:
        return Payment.model_validate(await self._http.request("/v1/payment", params))

    async def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payment:
        return Payment.model_validate(await self._http.request("/v1/payment/info", _lookup(uuid, order_id)))

    async def history(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, status: Optional[str] = None
    ) -> PaymentList:
        return PaymentList.model_validate(
            await self._http.request("/v1/payment/history", _clean(limit=limit, offset=offset, status=status))
        )

    async def services(self) -> List[ServiceMethod]:
        data = await self._http.request("/v1/payment/services", {})
        return [ServiceMethod.model_validate(x) for x in data]

    async def qr(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Dict[str, str]:
        return await self._http.request("/v1/payment/qr", _lookup(uuid, order_id))

    async def resend(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Any:
        return await self._http.request("/v1/payment/resend", _lookup(uuid, order_id))

    async def refund(self, **params: Any) -> Any:
        return await self._http.request("/v1/payment/refund", params)

    async def list_accepted(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payment/accepted/list", {})

    async def set_accepted(self, accepted: List[Dict[str, str]]) -> Any:
        return await self._http.request("/v1/payment/accepted/set", {"accepted": accepted})

    async def list_discounts(self) -> Any:
        return await self._http.request("/v1/payment/discount/list", {})

    async def set_discount(self, **params: Any) -> Any:
        return await self._http.request("/v1/payment/discount/set", params)

    async def get_accuracy(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payment/accuracy/get", {})

    async def set_accuracy(self, **params: Any) -> Any:
        return await self._http.request("/v1/payment/accuracy/set", params)

    async def get_autorefund(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payment/autorefund/get", {})

    async def set_autorefund(self, **params: Any) -> Any:
        return await self._http.request("/v1/payment/autorefund/set", params)


class Payouts(_Base):
    async def create(self, **params: Any) -> Payout:
        return Payout.model_validate(await self._http.request("/v1/payout", params))

    async def create_mass(self, payouts: List[Dict[str, Any]], source: Optional[str] = None) -> MassPayoutResult:
        body: Dict[str, Any] = {"payouts": payouts}
        if source is not None:
            body["source"] = source
        return MassPayoutResult.model_validate(await self._http.request("/v1/payout/mass", body))

    async def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payout:
        return Payout.model_validate(await self._http.request("/v1/payout/info", _lookup(uuid, order_id)))

    async def history(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, status: Optional[str] = None
    ) -> PayoutList:
        return PayoutList.model_validate(
            await self._http.request("/v1/payout/history", _clean(limit=limit, offset=offset, status=status))
        )

    async def services(self) -> List[ServiceMethod]:
        data = await self._http.request("/v1/payout/services", {})
        return [ServiceMethod.model_validate(x) for x in data]

    async def calculate(self, **params: Any) -> PayoutCalculation:
        return PayoutCalculation.model_validate(await self._http.request("/v1/payout/calculate", params))

    async def approve(self, uuid: str) -> Any:
        return await self._http.request("/v1/payout/approve", {"uuid": uuid})

    async def refund(self, **params: Any) -> Any:
        return await self._http.request("/v1/payment/refund", params)

    async def get_fee_config(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payout/fee-config/get", {})

    async def set_fee_config(self, fee_on_recipient: bool) -> Any:
        return await self._http.request("/v1/payout/fee-config/set", {"fee_on_recipient": fee_on_recipient})

    async def get_refund_fee_config(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payout/refund-fee-config/get", {})

    async def set_refund_fee_config(self, fee_on_customer: bool) -> Any:
        return await self._http.request("/v1/payout/refund-fee-config/set", {"fee_on_customer": fee_on_customer})


class Wallets(_Base):
    async def create(self, **params: Any) -> Wallet:
        return Wallet.model_validate(await self._http.request("/v1/wallet", params))

    async def block(self, *, address: str, is_force_block: Optional[bool] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"address": address}
        if is_force_block is not None:
            body["is_force_block"] = is_force_block
        return await self._http.request("/v1/wallet/block", body)

    async def blocked_address_refund(self, *, uuid: str, address: str) -> Any:
        return await self._http.request("/v1/wallet/blocked-address-refund", {"uuid": uuid, "address": address})

    async def qr(self, address: str) -> Dict[str, str]:
        return await self._http.request("/v1/wallet/qr", {"address": address})


class AccountResource(_Base):
    async def balance(self) -> Balance:
        data = await self._http.request("/v1/balance", {})
        return Balance.model_validate(data.get("balance", data))

    async def referral(self) -> ReferralInfo:
        return ReferralInfo.model_validate(await self._http.request("/v1/referral/info", {}))

    async def transfer_to_personal(self, **params: Any) -> Dict[str, Any]:
        return await self._http.request("/v1/transfer/to-personal", params)

    async def vrcs(self, enabled: Optional[bool] = None) -> Dict[str, Any]:
        body = {} if enabled is None else {"enabled": enabled}
        return await self._http.request("/v1/vrcs", body)


class WebhooksResource(_Base):
    async def register(self, url: str) -> WebhookRegistration:
        return WebhookRegistration.model_validate(await self._http.request("/v1/webhooks", {"url": url}))

    async def deliveries(self) -> List[Delivery]:
        data = await self._http.request("/v1/webhooks/deliveries", {})
        return [Delivery.model_validate(x) for x in data.get("deliveries", [])]

    async def test_payment(self, **params: Any) -> Dict[str, Any]:
        return await self._http.request("/v1/test-webhook/payment", params)

    async def test_wallet(self, **params: Any) -> Dict[str, Any]:
        return await self._http.request("/v1/test-webhook/wallet", params)

    async def test_payout(self, **params: Any) -> Dict[str, Any]:
        return await self._http.request("/v1/test-webhook/payout", params)


class Settings(_Base):
    async def list_auto_withdraw(self) -> List[AutoWithdrawRule]:
        data = await self._http.request("/v1/auto-withdraw/list", {})
        return [AutoWithdrawRule.model_validate(x) for x in data.get("rules", [])]

    async def set_auto_withdraw(self, **params: Any) -> Any:
        return await self._http.request("/v1/auto-withdraw/set", params)

    async def delete_auto_withdraw(self, currency: str) -> Any:
        return await self._http.request("/v1/auto-withdraw/delete", {"currency": currency})

    async def list_allowlist(self) -> Dict[str, Any]:
        return await self._http.request("/v1/api-allowlist/list", {})

    async def add_allowlist(self, cidr: str) -> Any:
        return await self._http.request("/v1/api-allowlist/add", {"cidr": cidr})

    async def remove_allowlist(self, cidr: str) -> Any:
        return await self._http.request("/v1/api-allowlist/remove", {"cidr": cidr})

    async def enable_allowlist(self, enabled: bool) -> Any:
        return await self._http.request("/v1/api-allowlist/enable", {"enabled": enabled})


class Rates(_Base):
    async def list(self, currency_from: Optional[str] = None) -> List[ExchangeRate]:
        body = {"currency_from": currency_from} if currency_from else {}
        data = await self._http.request_public("/v1/exchange-rate/list", body)
        return [ExchangeRate(**x) for x in data]

    async def currencies(self) -> List[Currency]:
        """Публичный каталог активов и сетей. ``GET /v1/currencies`` (без подписи)."""
        data = await self._http.request_public("/v1/currencies", method="GET")
        return [Currency(**x) for x in data.get("currencies", [])]
