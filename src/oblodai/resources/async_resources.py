"""Асинхронные ресурсы. Зеркало sync_resources с await; хелперы переиспользуются."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .._http import AsyncHTTPClient
from ..models import (
    Currency,
    AutoWithdrawRule,
    Balance,
    BatchInfo,
    BatchSubmitResult,
    Delivery,
    ExchangeRate,
    MassPayoutResult,
    Payment,
    PaymentLink,
    PaymentLinkCreated,
    PaymentLinkInfo,
    PaymentList,
    PaymentResolution,
    Payout,
    PayoutCalculation,
    PayoutLink,
    PayoutLinkBatchResult,
    PayoutLinkClaimInfo,
    PayoutLinkClaimResult,
    PayoutLinkCreated,
    PayoutList,
    ReferralInfo,
    SandboxDelivery,
    SandboxDeposit,
    SandboxFaucetResult,
    SandboxReplayResult,
    SandboxResetResult,
    ServiceMethod,
    SplitRule,
    SplitRuleCreated,
    TransferToUserResult,
    Wallet,
    WebhookRegistration,
)
from .sync_resources import _clean, _idem_key, _lookup, _pop_idem_key


class _Base:
    def __init__(self, http: AsyncHTTPClient) -> None:
        self._http = http


class Payments(_Base):
    async def create(self, **params: Any) -> Payment:
        """См. sync :meth:`~oblodai.resources.sync_resources.Payments.create`:
        ``Idempotency-Key`` авто-uuid4 (стабилен между ретраями), свой — ``idempotency_key``;
        ``order_id`` уходит как есть."""
        key = _pop_idem_key(params)
        return Payment.model_validate(await self._http.request("/v1/payment", params, idempotency_key=key))

    async def create_batch(
        self,
        payments: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Пачка платежей (до 5000). ``POST /v1/payment/batch``. ``order_id`` обязателен на item."""
        body: Dict[str, Any] = {"payments": payments}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            await self._http.request("/v1/payment/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

    async def refund_batch(
        self,
        refunds: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Синоним ``client.refunds.create_batch``."""
        body: Dict[str, Any] = {"refunds": refunds}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            await self._http.request("/v1/refund/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

    async def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payment:
        return Payment.model_validate(await self._http.request("/v1/payment/info", _lookup(uuid, order_id)))

    async def public_get(self, payment_id: str) -> Payment:
        """ПУБЛИЧНО (без подписи): состояние инвойса для кастомной страницы оплаты.
        ``GET /v1/pay/{id}``. В статусе ``select`` дополнительно приходит ``accepted``."""
        return Payment.model_validate(await self._http.request_public(f"/v1/pay/{payment_id}", method="GET"))

    async def public_select(self, payment_id: str, *, currency: str, network: str) -> Payment:
        """ПУБЛИЧНО (без подписи): выбор валюты+сети для валюто-агностичного инвойса.
        ``POST /v1/pay/{id}/select``. Ответ — финализированный платёж."""
        return Payment.model_validate(
            await self._http.request_public(f"/v1/pay/{payment_id}/select", {"currency": currency, "network": network})
        )

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
        """Возврат; с v1.1.0 ``address`` необязателен (дефолт — ``payer_address``, кроме UTXO).
        Идемпотентность — заголовком ``Idempotency-Key`` (``idempotency_key`` в тело не попадает)."""
        key = _pop_idem_key(params)
        return await self._http.request("/v1/payment/refund", params, idempotency_key=key)

    async def resolve(
        self,
        *,
        uuid: Optional[str] = None,
        order_id: Optional[str] = None,
        action: str,
        address: Optional[str] = None,
        network: Optional[str] = None,
        reference: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentResolution:
        """Судьба недоплаченного платежа: ``action="accept"`` | ``"refund"``. ``POST /v1/payment/resolve``."""
        body = _clean(uuid=uuid, order_id=order_id, action=action, address=address,
                      network=network, reference=reference)
        return PaymentResolution.model_validate(
            await self._http.request("/v1/payment/resolve", body, idempotency_key=_idem_key(idempotency_key))
        )

    async def send_email(
        self, *, uuid: Optional[str] = None, order_id: Optional[str] = None, email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Письмо-счёт покупателю. ``POST /v1/payment/send-email``. Получатель — ``email`` или ``payer_email``."""
        body = _lookup(uuid, order_id)
        if email is not None:
            body["email"] = email
        return await self._http.request("/v1/payment/send-email", body)

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


class Refunds(_Base):
    async def create_batch(
        self,
        refunds: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Пачка возвратов (до 5000). ``POST /v1/refund/batch``.
        На item обязательны ``reference`` и ``uuid``/``order_id`` инвойса."""
        body: Dict[str, Any] = {"refunds": refunds}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            await self._http.request("/v1/refund/batch", body, idempotency_key=_idem_key(idempotency_key))
        )


class Payouts(_Base):
    async def create(self, **params: Any) -> Payout:
        key = _pop_idem_key(params)
        return Payout.model_validate(await self._http.request("/v1/payout", params, idempotency_key=key))

    async def create_mass(
        self,
        payouts: List[Dict[str, Any]],
        source: Optional[str] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> MassPayoutResult:
        body: Dict[str, Any] = {"payouts": payouts}
        if source is not None:
            body["source"] = source
        return MassPayoutResult.model_validate(
            await self._http.request("/v1/payout/mass", body, idempotency_key=_idem_key(idempotency_key))
        )

    async def create_batch(
        self,
        payouts: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Пачка выплат (до 5000). ``POST /v1/payout/batch``. ``order_id`` обязателен на item."""
        body: Dict[str, Any] = {"payouts": payouts}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            await self._http.request("/v1/payout/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

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
        key = _pop_idem_key(params)
        return await self._http.request("/v1/payment/refund", params, idempotency_key=key)

    async def get_fee_config(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payout/fee-config/get", {})

    async def set_fee_config(self, fee_on_recipient: bool) -> Any:
        return await self._http.request("/v1/payout/fee-config/set", {"fee_on_recipient": fee_on_recipient})

    async def get_refund_fee_config(self) -> Dict[str, Any]:
        return await self._http.request("/v1/payout/refund-fee-config/get", {})

    async def set_refund_fee_config(self, fee_on_customer: bool) -> Any:
        return await self._http.request("/v1/payout/refund-fee-config/set", {"fee_on_customer": fee_on_customer})


class Batches(_Base):
    async def info(self, batch_id: str, *, limit: Optional[int] = None, offset: Optional[int] = None) -> BatchInfo:
        """Прогресс и по-элементные результаты пачки. ``POST /v1/batch/info``."""
        body: Dict[str, Any] = {"batch_id": batch_id}
        if limit is not None:
            body["limit"] = limit
        if offset is not None:
            body["offset"] = offset
        return BatchInfo.model_validate(await self._http.request("/v1/batch/info", body))


class PaymentLinks(_Base):
    """Платёжные ссылки. Management-эндпоинты не используют ``Idempotency-Key``."""

    async def create(self, **params: Any) -> PaymentLinkCreated:
        return PaymentLinkCreated.model_validate(await self._http.request("/v1/payment/link", params))

    async def list(self, *, limit: Optional[int] = None, offset: Optional[int] = None) -> List[PaymentLink]:
        data = await self._http.request("/v1/payment/link/list", _clean(limit=limit, offset=offset))
        return [PaymentLink.model_validate(x) for x in data.get("items", [])]

    async def info(self, link_id: str) -> PaymentLinkInfo:
        return PaymentLinkInfo.model_validate(await self._http.request("/v1/payment/link/info", {"link_id": link_id}))

    async def toggle(self, link_id: str, active: bool) -> Dict[str, Any]:
        return await self._http.request("/v1/payment/link/toggle", {"link_id": link_id, "active": active})

    async def public_get(self, link_id: str) -> Any:
        """Публичные данные ссылки (без подписи). ``GET /v1/link/{id}``."""
        return await self._http.request_public(f"/v1/link/{link_id}", method="GET")

    async def checkout(self, link_id: str, **params: Any) -> Payment:
        """Публичный checkout (без подписи). ``POST /v1/link/{id}/checkout``. Ответ — обычный платёж."""
        return Payment.model_validate(await self._http.request_public(f"/v1/link/{link_id}/checkout", params))


class Splits(_Base):
    async def create_rule(self, **params: Any) -> SplitRuleCreated:
        """``{address, network}`` XOR ``{merchant_id}`` + ``percent`` (+ ``note``). ``POST /v1/split/rule``."""
        return SplitRuleCreated.model_validate(await self._http.request("/v1/split/rule", params))

    async def split_to_address(
        self, *, address: str, network: str, percent: float, note: Optional[str] = None
    ) -> SplitRuleCreated:
        return await self.create_rule(**_clean(address=address, network=network, percent=percent, note=note))

    async def split_to_merchant(
        self, *, merchant_id: str, percent: float, note: Optional[str] = None
    ) -> SplitRuleCreated:
        return await self.create_rule(**_clean(merchant_id=merchant_id, percent=percent, note=note))

    async def list_rules(self) -> List[SplitRule]:
        data = await self._http.request("/v1/split/rule/list", {})
        return [SplitRule.model_validate(x) for x in data.get("items", [])]

    async def delete_rule(self, rule_id: str) -> Dict[str, Any]:
        return await self._http.request("/v1/split/rule/delete", {"rule_id": rule_id})

    async def get_config(self) -> Dict[str, Any]:
        return await self._http.request("/v1/split/config/get", {})

    async def set_config(self, *, refund_hold_hours: int) -> Dict[str, Any]:
        return await self._http.request("/v1/split/config/set", {"refund_hold_hours": refund_hold_hours})


class PayoutLinks(_Base):
    """Payout-ссылки («крипто-чеки»). ``/v1/payout/link*`` НЕ принимают ``Idempotency-Key`` —
    дедупликация через per-link ``reference``. Требуют PAYOUT/API-ключ."""

    async def create(self, **params: Any) -> PayoutLinkCreated:
        """``POST /v1/payout/link``. Рекомендуем задавать ``expires_in_hours`` ЯВНО (1–720):
        при отсутствии/0 бэкенд клампит срок к 1 часу. ``claim_token``/``claim_url`` —
        только в этом ответе."""
        return PayoutLinkCreated.model_validate(await self._http.request("/v1/payout/link", params))

    async def create_batch(self, links: List[Dict[str, Any]]) -> PayoutLinkBatchResult:
        """Пачка ссылок (до 500), index-aligned ответ. ``POST /v1/payout/link/batch``."""
        return PayoutLinkBatchResult.model_validate(
            await self._http.request("/v1/payout/link/batch", {"links": links})
        )

    async def list(self, *, limit: Optional[int] = None, offset: Optional[int] = None) -> List[PayoutLink]:
        data = await self._http.request("/v1/payout/link/list", _clean(limit=limit, offset=offset))
        return [PayoutLink.model_validate(x) for x in data.get("links", [])]

    async def info(self, link_id: str) -> PayoutLink:
        return PayoutLink.model_validate(await self._http.request("/v1/payout/link/info", {"link_id": link_id}))

    async def cancel(self, link_id: str) -> PayoutLink:
        return PayoutLink.model_validate(await self._http.request("/v1/payout/link/cancel", {"link_id": link_id}))

    async def claim_info(self, token: str) -> PayoutLinkClaimInfo:
        """ПУБЛИЧНО (без подписи). ``GET /v1/claim/{token}``."""
        return PayoutLinkClaimInfo.model_validate(
            await self._http.request_public(f"/v1/claim/{token}", method="GET")
        )

    async def claim(self, token: str, *, address: str, memo: Optional[str] = None) -> PayoutLinkClaimResult:
        """ПУБЛИЧНО (без подписи): забрать средства на ``address``. ``POST /v1/claim/{token}``."""
        body: Dict[str, Any] = {"address": address}
        if memo is not None:
            body["memo"] = memo
        return PayoutLinkClaimResult.model_validate(await self._http.request_public(f"/v1/claim/{token}", body))


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
        """Идемпотентность — заголовком ``Idempotency-Key`` (авто-uuid4; свой — ``idempotency_key``)."""
        key = _pop_idem_key(params)
        return await self._http.request("/v1/transfer/to-personal", params, idempotency_key=key)

    async def transfer_to_user(
        self,
        *,
        to_user_id: str,
        amount: str,
        currency: str,
        order_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> TransferToUserResult:
        """Внутренний перевод без комиссии пользователю платформы. ``POST /v1/transfer/to-user``.
        ``to_user_id`` — id пользователя (UUID), НЕ username. Идемпотентность — лестница
        как у прочих денежных эндпоинтов: заголовок ``Idempotency-Key`` (авто-uuid4;
        свой — ``idempotency_key``), иначе ``order_id``, иначе подпись запроса."""
        body = _clean(to_user_id=to_user_id, amount=amount, currency=currency, order_id=order_id)
        return TransferToUserResult.model_validate(
            await self._http.request("/v1/transfer/to-user", body, idempotency_key=_idem_key(idempotency_key))
        )

    async def transfer_batch(
        self,
        transfers: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Пачка переводов to-user (до 5000). ``POST /v1/transfer/batch``. Каждый item —
        тело обычного :meth:`transfer_to_user`; результаты — через
        ``client.batches.info(batch_id)``."""
        body: Dict[str, Any] = {"transfers": transfers}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            await self._http.request("/v1/transfer/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

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


class Sandbox(_Base):
    """Песочница разработчика — ТОЛЬКО для тестовых ключей.
    См. sync :class:`~oblodai.resources.sync_resources.Sandbox`: живой ключ получает
    HTTP 403 ``sandbox.live_key``; не используйте эту группу в продакшн-коде."""

    async def simulate_deposit(
        self,
        *,
        invoice_id: str,
        amount: Optional[str] = None,
        confirmations: Optional[int] = None,
        txid: Optional[str] = None,
    ) -> SandboxDeposit:
        """Имитирует он-чейн депозит в инвойс. ``POST /v1/sandbox/deposit``.
        Семантика параметров — как у sync-версии."""
        body = _clean(invoice_id=invoice_id, amount=amount, confirmations=confirmations, txid=txid)
        return SandboxDeposit.model_validate(await self._http.request("/v1/sandbox/deposit", body))

    async def faucet(
        self, *, asset: str, amount: str, idempotency_key: Optional[str] = None
    ) -> SandboxFaucetResult:
        """Кран тестового баланса. ``POST /v1/sandbox/faucet``. ``amount`` ≤ 1000000 за вызов;
        ``idempotency_key`` — поле ТЕЛА запроса (контракт эндпоинта), не заголовок."""
        body = _clean(asset=asset, amount=amount, idempotency_key=idempotency_key)
        return SandboxFaucetResult.model_validate(await self._http.request("/v1/sandbox/faucet", body))

    async def reset(self) -> SandboxResetResult:
        """Отменяет открытые инвойсы и обнуляет балансы (история сохраняется).
        ``POST /v1/sandbox/reset``."""
        return SandboxResetResult.model_validate(await self._http.request("/v1/sandbox/reset", {}))

    async def list_webhooks(self) -> List[SandboxDelivery]:
        """Недавние доставки вебхуков (до 50, новые первыми). Подписанный ``GET``
        с пустым телом: ``{ts}\\nGET\\n/v1/sandbox/webhooks\\n``."""
        data = await self._http.request("/v1/sandbox/webhooks", method="GET")
        return [SandboxDelivery.model_validate(x) for x in data.get("deliveries", [])]

    async def replay_webhook(self, delivery_id: str) -> SandboxReplayResult:
        """Перепоставляет одну доставку в очередь. ``POST /v1/sandbox/webhooks/replay``."""
        return SandboxReplayResult.model_validate(
            await self._http.request("/v1/sandbox/webhooks/replay", {"delivery_id": delivery_id})
        )


class Rates(_Base):
    async def list(self, currency_from: Optional[str] = None) -> List[ExchangeRate]:
        body = {"currency_from": currency_from} if currency_from else {}
        data = await self._http.request_public("/v1/exchange-rate/list", body)
        return [ExchangeRate(**x) for x in data]

    async def currencies(self) -> List[Currency]:
        """Публичный каталог активов и сетей. ``GET /v1/currencies`` (без подписи)."""
        data = await self._http.request_public("/v1/currencies", method="GET")
        return [Currency(**x) for x in data.get("currencies", [])]
