"""Синхронные ресурсы (группы методов). Тонкие обёртки над SyncHTTPClient + разбор в pydantic-модели."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .._http import SyncHTTPClient
from ..models import (
    Currency,
    AcceptedMethod,
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


class _Base:
    def __init__(self, http: SyncHTTPClient) -> None:
        self._http = http


class Payments(_Base):
    def create(self, **params: Any) -> Payment:
        return Payment.model_validate(self._http.request("/v1/payment", _with_idempotency(params)))

    def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payment:
        return Payment.model_validate(self._http.request("/v1/payment/info", _lookup(uuid, order_id)))

    def history(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, status: Optional[str] = None
    ) -> PaymentList:
        return PaymentList.model_validate(
            self._http.request("/v1/payment/history", _clean(limit=limit, offset=offset, status=status))
        )

    def services(self) -> List[ServiceMethod]:
        data = self._http.request("/v1/payment/services", {})
        return [ServiceMethod.model_validate(x) for x in data]

    def qr(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Dict[str, str]:
        return self._http.request("/v1/payment/qr", _lookup(uuid, order_id))

    def resend(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Any:
        return self._http.request("/v1/payment/resend", _lookup(uuid, order_id))

    def refund(self, **params: Any) -> Any:
        return self._http.request("/v1/payment/refund", params)

    def list_accepted(self) -> Dict[str, Any]:
        return self._http.request("/v1/payment/accepted/list", {})

    def set_accepted(self, accepted: List[Dict[str, str]]) -> Any:
        return self._http.request("/v1/payment/accepted/set", {"accepted": accepted})

    def list_discounts(self) -> Any:
        return self._http.request("/v1/payment/discount/list", {})

    def set_discount(self, **params: Any) -> Any:
        return self._http.request("/v1/payment/discount/set", params)

    def get_accuracy(self) -> Dict[str, Any]:
        return self._http.request("/v1/payment/accuracy/get", {})

    def set_accuracy(self, **params: Any) -> Any:
        return self._http.request("/v1/payment/accuracy/set", params)

    def get_autorefund(self) -> Dict[str, Any]:
        return self._http.request("/v1/payment/autorefund/get", {})

    def set_autorefund(self, **params: Any) -> Any:
        return self._http.request("/v1/payment/autorefund/set", params)


class Payouts(_Base):
    def create(self, **params: Any) -> Payout:
        return Payout.model_validate(self._http.request("/v1/payout", params))

    def create_mass(self, payouts: List[Dict[str, Any]], source: Optional[str] = None) -> MassPayoutResult:
        body: Dict[str, Any] = {"payouts": payouts}
        if source is not None:
            body["source"] = source
        return MassPayoutResult.model_validate(self._http.request("/v1/payout/mass", body))

    def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payout:
        return Payout.model_validate(self._http.request("/v1/payout/info", _lookup(uuid, order_id)))

    def history(
        self, *, limit: Optional[int] = None, offset: Optional[int] = None, status: Optional[str] = None
    ) -> PayoutList:
        return PayoutList.model_validate(
            self._http.request("/v1/payout/history", _clean(limit=limit, offset=offset, status=status))
        )

    def services(self) -> List[ServiceMethod]:
        data = self._http.request("/v1/payout/services", {})
        return [ServiceMethod.model_validate(x) for x in data]

    def calculate(self, **params: Any) -> PayoutCalculation:
        return PayoutCalculation.model_validate(self._http.request("/v1/payout/calculate", params))

    def approve(self, uuid: str) -> Any:
        return self._http.request("/v1/payout/approve", {"uuid": uuid})

    def refund(self, **params: Any) -> Any:
        return self._http.request("/v1/payment/refund", params)

    def get_fee_config(self) -> Dict[str, Any]:
        return self._http.request("/v1/payout/fee-config/get", {})

    def set_fee_config(self, fee_on_recipient: bool) -> Any:
        return self._http.request("/v1/payout/fee-config/set", {"fee_on_recipient": fee_on_recipient})

    def get_refund_fee_config(self) -> Dict[str, Any]:
        return self._http.request("/v1/payout/refund-fee-config/get", {})

    def set_refund_fee_config(self, fee_on_customer: bool) -> Any:
        return self._http.request("/v1/payout/refund-fee-config/set", {"fee_on_customer": fee_on_customer})


class Wallets(_Base):
    def create(self, **params: Any) -> Wallet:
        return Wallet.model_validate(self._http.request("/v1/wallet", params))

    def block(self, *, address: str, is_force_block: Optional[bool] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"address": address}
        if is_force_block is not None:
            body["is_force_block"] = is_force_block
        return self._http.request("/v1/wallet/block", body)

    def blocked_address_refund(self, *, uuid: str, address: str) -> Any:
        return self._http.request("/v1/wallet/blocked-address-refund", {"uuid": uuid, "address": address})

    def qr(self, address: str) -> Dict[str, str]:
        return self._http.request("/v1/wallet/qr", {"address": address})


class AccountResource(_Base):
    def balance(self) -> Balance:
        data = self._http.request("/v1/balance", {})
        # ответ: { "balance": { "merchant": [...] } }
        return Balance.model_validate(data.get("balance", data))

    def referral(self) -> ReferralInfo:
        return ReferralInfo.model_validate(self._http.request("/v1/referral/info", {}))

    def transfer_to_personal(self, **params: Any) -> Dict[str, Any]:
        return self._http.request("/v1/transfer/to-personal", _with_idempotency(params))

    def vrcs(self, enabled: Optional[bool] = None) -> Dict[str, Any]:
        body = {} if enabled is None else {"enabled": enabled}
        return self._http.request("/v1/vrcs", body)


class WebhooksResource(_Base):
    def register(self, url: str) -> WebhookRegistration:
        return WebhookRegistration.model_validate(self._http.request("/v1/webhooks", {"url": url}))

    def deliveries(self) -> List[Delivery]:
        data = self._http.request("/v1/webhooks/deliveries", {})
        return [Delivery.model_validate(x) for x in data.get("deliveries", [])]

    def test_payment(self, **params: Any) -> Dict[str, Any]:
        return self._http.request("/v1/test-webhook/payment", params)

    def test_wallet(self, **params: Any) -> Dict[str, Any]:
        return self._http.request("/v1/test-webhook/wallet", params)

    def test_payout(self, **params: Any) -> Dict[str, Any]:
        return self._http.request("/v1/test-webhook/payout", params)


class Settings(_Base):
    def list_auto_withdraw(self) -> List[AutoWithdrawRule]:
        data = self._http.request("/v1/auto-withdraw/list", {})
        return [AutoWithdrawRule.model_validate(x) for x in data.get("rules", [])]

    def set_auto_withdraw(self, **params: Any) -> Any:
        return self._http.request("/v1/auto-withdraw/set", params)

    def delete_auto_withdraw(self, currency: str) -> Any:
        return self._http.request("/v1/auto-withdraw/delete", {"currency": currency})

    def list_allowlist(self) -> Dict[str, Any]:
        return self._http.request("/v1/api-allowlist/list", {})

    def add_allowlist(self, cidr: str) -> Any:
        return self._http.request("/v1/api-allowlist/add", {"cidr": cidr})

    def remove_allowlist(self, cidr: str) -> Any:
        return self._http.request("/v1/api-allowlist/remove", {"cidr": cidr})

    def enable_allowlist(self, enabled: bool) -> Any:
        return self._http.request("/v1/api-allowlist/enable", {"enabled": enabled})


class Rates(_Base):
    def list(self, currency_from: Optional[str] = None) -> List[ExchangeRate]:
        body = {"currency_from": currency_from} if currency_from else {}
        data = self._http.request_public("/v1/exchange-rate/list", body)
        return [ExchangeRate(**x) for x in data]

    def currencies(self) -> List[Currency]:
        """Публичный каталог активов и сетей. ``GET /v1/currencies`` (без подписи)."""
        data = self._http.request_public("/v1/currencies", method="GET")
        return [Currency(**x) for x in data.get("currencies", [])]


# ── Хелперы ──


def _with_idempotency(params: Dict[str, Any]) -> Dict[str, Any]:
    """Гарантирует стабильный ключ идемпотентности ``order_id`` для не-идемпотентных POST.

    Клиент повторяет POST и переподписывает КАЖДУЮ попытку; бэкенд дедуплицирует платежи и
    переводы по ``order_id`` (для переводов сигнатурный fallback ломается переподписью). Если
    вызывающий не задал непустой ``order_id`` — подставляем его один раз (мутируем переданный
    ``params``), чтобы все попытки ретрая использовали тот же ключ и не создавали дубль.
    """
    if not params.get("order_id"):
        params["order_id"] = "idem-" + uuid.uuid4().hex
    return params


def _lookup(uuid: Optional[str], order_id: Optional[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if uuid is not None:
        out["uuid"] = uuid
    if order_id is not None:
        out["order_id"] = order_id
    return out


def _clean(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}
