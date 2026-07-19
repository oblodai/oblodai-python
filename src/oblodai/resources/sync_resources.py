"""Синхронные ресурсы (группы методов). Тонкие обёртки над SyncHTTPClient + разбор в pydantic-модели."""

from __future__ import annotations

import uuid as _uuid
from typing import Any, Dict, List, Optional

from .._http import SyncHTTPClient
from .._params import (
    PAYMENT_FIELDS,
    PAYMENT_LINK_FIELDS,
    PAYOUT_FIELDS,
    PAYOUT_LINK_FIELDS,
    SPLIT_RULE_FIELDS,
    check_params,
)
from ..models import (
    Currency,
    AcceptedMethod,
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


class _Base:
    def __init__(self, http: SyncHTTPClient) -> None:
        self._http = http


class Payments(_Base):
    def create(self, **params: Any) -> Payment:
        """Создаёт платёж. ``POST /v1/payment``.

        Идемпотентность (v1.1.0): SDK генерирует заголовок ``Idempotency-Key`` (uuid4) один
        раз на вызов — он одинаков во всех внутренних ретраях, поэтому повтор после
        таймаута/5xx не создаст дубль. Свой ключ передаётся kwarg'ом ``idempotency_key``
        (уходит в заголовок, в тело запроса не попадает). ``order_id`` — ваш
        бизнес-идентификатор: уходит как есть, SDK его больше НЕ подставляет.

        Имена полей проверяются по белому списку (:data:`oblodai._params.PAYMENT_FIELDS`) ДО
        подписи и отправки: неизвестное имя — ``TypeError``, а не молча изменённая денежная
        операция. Допустимые поля: ``amount``, ``currency``, ``order_id``, ``network``,
        ``to_currency``, ``lifetime``, ``subtract``, ``accuracy_payment_percent``,
        ``url_callback``, ``url_return``, ``url_success``, ``additional_data``,
        ``payer_email``, ``theme``, ``is_payment_multiple``, ``is_refresh``
        (плюс SDK-kwarg ``idempotency_key``).
        """
        check_params("payments.create", params, PAYMENT_FIELDS)
        key = _pop_idem_key(params)
        return Payment.model_validate(self._http.request("/v1/payment", params, idempotency_key=key))

    def create_batch(
        self,
        payments: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Ставит пачку платежей (до 5000) одним запросом. ``POST /v1/payment/batch``.

        Каждый item — тело обычного ``payments.create``; ``order_id`` обязателен на каждом
        item (ключ дедупликации внутри пачки). ``on_error`` — ``"continue"`` (по умолчанию)
        или ``"stop"``. Обработка в фоне: результаты по каждому элементу — через
        ``client.batches.info(batch_id)``. Идемпотентность — заголовком ``Idempotency-Key``
        (генерируется автоматически, свой — через ``idempotency_key``).
        """
        body: Dict[str, Any] = {"payments": payments}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            self._http.request("/v1/payment/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

    def refund_batch(
        self,
        refunds: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Ставит пачку возвратов (до 5000). ``POST /v1/refund/batch``. КАНОНИЧЕСКИЙ путь.

        На каждом item обязательны ``reference`` (per-refund ключ дедупликации) и
        ``uuid``/``order_id`` инвойса. ``on_error`` — ``"continue"`` (по умолчанию) или
        ``"stop"``. Результаты — через ``client.batches.info(batch_id)``. Идемпотентность —
        заголовком ``Idempotency-Key`` (авто-uuid4; свой — ``idempotency_key``).

        Устаревший синоним — ``client.refunds.create_batch(...)`` (тот же эндпоинт, то же тело);
        он есть только в Python SDK и при обращении выдаёт ``DeprecationWarning``.
        """
        body: Dict[str, Any] = {"refunds": refunds}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            self._http.request("/v1/refund/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

    def info(self, *, uuid: Optional[str] = None, order_id: Optional[str] = None) -> Payment:
        return Payment.model_validate(self._http.request("/v1/payment/info", _lookup(uuid, order_id)))

    def public_get(self, payment_id: str) -> Payment:
        """ПУБЛИЧНО (без подписи): состояние инвойса для СВОЕЙ (кастомной) страницы оплаты.
        ``GET /v1/pay/{id}`` — та же публичная семья, что ``/v1/link/{id}`` и claim.

        Возвращает только покупательские поля (адрес, сумма, QR, статус, срок) — без
        секрета мерчанта, поэтому метод можно звать прямо из браузера. Для
        валюто-агностичного инвойса в статусе ``select`` дополнительно приходит
        ``accepted`` — методы (валюта+сеть) на выбор; финализация — :meth:`public_select`.
        """
        return Payment.model_validate(self._http.request_public(f"/v1/pay/{payment_id}", method="GET"))

    def public_select(self, payment_id: str, *, currency: str, network: str) -> Payment:
        """ПУБЛИЧНО (без подписи): покупатель выбирает валюту+сеть для валюто-агностичного
        инвойса на кастомной странице оплаты. ``POST /v1/pay/{id}/select``.

        Фиксирует курс, выделяет депозитный адрес и переводит инвойс из ``select`` в
        ``created``. Пара должна входить в accepted-набор мерчанта (или полный каталог,
        если набор не настроен). Ответ — финализированный платёж (обычная модель).
        """
        return Payment.model_validate(
            self._http.request_public(f"/v1/pay/{payment_id}/select", {"currency": currency, "network": network})
        )

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
        """Возврат по платежу. ``POST /v1/payment/refund``.

        С v1.1.0 ``address`` необязателен — по умолчанию возврат уходит на адрес плательщика
        (``payer_address``); для UTXO-сетей (Bitcoin и т. п.), где адрес плательщика неизвестен,
        ``address`` по-прежнему обязателен. Идемпотентность — заголовком ``Idempotency-Key``
        (авто-uuid4, стабилен между ретраями; свой — kwarg ``idempotency_key``).
        """
        key = _pop_idem_key(params)
        return self._http.request("/v1/payment/refund", params, idempotency_key=key)

    def resolve(
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
        """Решает судьбу НЕДОПЛАЧЕННОГО платежа (статус ``wrong_amount``). ``POST /v1/payment/resolve``.

        ``action="accept"`` — оставить частичную оплату себе (глушит авто-возврат);
        ``action="refund"`` — вернуть плательщику (``address`` по умолчанию — записанный
        ``payer_address`` инвойса; ``reference`` — per-refund ключ дедупликации).
        Требует PAYOUT/API-ключ. Идемпотентность — заголовком ``Idempotency-Key``
        (авто-uuid4, стабилен между ретраями; свой — ``idempotency_key``).
        """
        body = _clean(uuid=uuid, order_id=order_id, action=action, address=address,
                      network=network, reference=reference)
        return PaymentResolution.model_validate(
            self._http.request("/v1/payment/resolve", body, idempotency_key=_idem_key(idempotency_key))
        )

    def send_email(
        self, *, uuid: Optional[str] = None, order_id: Optional[str] = None, email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Отправляет покупателю письмо-счёт с кнопкой «Оплатить». ``POST /v1/payment/send-email``.

        Получатель — ``email``, а если он не задан — ``payer_email`` платежа
        (иначе ``email.no_recipient``). Лимит: 10 писем/час на адрес получателя.
        """
        body = _lookup(uuid, order_id)
        if email is not None:
            body["email"] = email
        return self._http.request("/v1/payment/send-email", body)

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


class Refunds(_Base):
    """УСТАРЕВШАЯ группа (``client.refunds``). Канон — ``client.payments.refund_batch(...)``.

    Дублирует ``Payments.refund_batch``: тот же ``POST /v1/refund/batch``, то же тело, та же
    идемпотентность — и существует только в Python SDK. Обращение к ``client.refunds`` выдаёт
    ``DeprecationWarning``; сама группа не удалена и работает как раньше.
    """

    def create_batch(
        self,
        refunds: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """УСТАРЕЛО — используйте :meth:`Payments.refund_batch`. Пачка возвратов (до 5000).

        ``POST /v1/refund/batch``. На каждом item обязательны ``reference`` (per-refund ключ
        дедупликации) и ``uuid``/``order_id`` инвойса. ``on_error`` — ``"continue"``
        (по умолчанию) или ``"stop"``. Результаты — через ``client.batches.info(batch_id)``.
        """
        body: Dict[str, Any] = {"refunds": refunds}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            self._http.request("/v1/refund/batch", body, idempotency_key=_idem_key(idempotency_key))
        )


class Payouts(_Base):
    def create(self, **params: Any) -> Payout:
        """Создаёт выплату. ``POST /v1/payout``. ``order_id`` обязателен (требование API).

        Идемпотентность (v1.1.0): заголовок ``Idempotency-Key`` — авто-uuid4, одинаков во
        всех внутренних ретраях; свой ключ — kwarg ``idempotency_key`` (в тело не попадает).

        Имена полей проверяются по белому списку (:data:`oblodai._params.PAYOUT_FIELDS`) ДО
        подписи и отправки: неизвестное имя — ``TypeError``. Допустимые поля: ``amount``,
        ``currency``, ``order_id``, ``address``, ``network``, ``is_subtract``, ``memo``,
        ``url_callback``, ``from_currency``, ``source`` (плюс SDK-kwarg ``idempotency_key``).
        """
        check_params("payouts.create", params, PAYOUT_FIELDS)
        key = _pop_idem_key(params)
        return Payout.model_validate(self._http.request("/v1/payout", params, idempotency_key=key))

    def create_mass(
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
            self._http.request("/v1/payout/mass", body, idempotency_key=_idem_key(idempotency_key))
        )

    def create_batch(
        self,
        payouts: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Ставит пачку выплат (до 5000). ``POST /v1/payout/batch``.

        ``order_id`` обязателен на каждом item (ключ дедупликации внутри пачки).
        ``on_error`` — ``"continue"`` (по умолчанию) или ``"stop"``. Результаты — через
        ``client.batches.info(batch_id)``. Идемпотентность — заголовком ``Idempotency-Key``
        (авто-uuid4; свой — ``idempotency_key``).
        """
        body: Dict[str, Any] = {"payouts": payouts}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            self._http.request("/v1/payout/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

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
        """Одобряет ожидающую выплату. ``POST /v1/payout/approve``.

        Это переход состояния, а не создание: шлюз принимает только выплату в статусе
        ``pending``, иначе отвечает 409 ``payout.not_pending``. Повторный approve не может
        одобрить или сдвинуть деньги дважды, поэтому заголовок идемпотентности здесь не
        нужен и не шлётся. Читайте 409 ``payout.not_pending`` как «уже одобрено» (не как
        сбой) и уточняйте фактический статус через :meth:`info` (``/v1/payout/info``).
        """
        return self._http.request("/v1/payout/approve", {"uuid": uuid})

    def refund(self, **params: Any) -> Any:
        """Синоним ``payments.refund`` (``POST /v1/payment/refund``); та же идемпотентность."""
        key = _pop_idem_key(params)
        return self._http.request("/v1/payment/refund", params, idempotency_key=key)

    def get_fee_config(self) -> Dict[str, Any]:
        return self._http.request("/v1/payout/fee-config/get", {})

    def set_fee_config(self, fee_on_recipient: bool) -> Any:
        return self._http.request("/v1/payout/fee-config/set", {"fee_on_recipient": fee_on_recipient})

    def get_refund_fee_config(self) -> Dict[str, Any]:
        return self._http.request("/v1/payout/refund-fee-config/get", {})

    def set_refund_fee_config(self, fee_on_customer: bool) -> Any:
        return self._http.request("/v1/payout/refund-fee-config/set", {"fee_on_customer": fee_on_customer})


class Batches(_Base):
    def info(self, batch_id: str, *, limit: Optional[int] = None, offset: Optional[int] = None) -> BatchInfo:
        """Прогресс и по-элементные результаты пачки. ``POST /v1/batch/info``.

        ``limit`` ≤ 0 или > 500 сервер заменяет на 100. ``info.done`` — ``True``, когда
        ``status == "completed"``; ``items[i].result`` — байт-в-байт result единичного
        эндпоинта, ``items[i].error`` — код ошибки элемента.
        """
        body: Dict[str, Any] = {"batch_id": batch_id}
        if limit is not None:
            body["limit"] = limit
        if offset is not None:
            body["offset"] = offset
        return BatchInfo.model_validate(self._http.request("/v1/batch/info", body))


class PaymentLinks(_Base):
    """Платёжные ссылки: переиспользуемая ссылка, по которой платят много людей.

    Management-эндпоинты НЕ используют ``Idempotency-Key`` (создание ссылки не двигает деньги).
    """

    def create(self, **params: Any) -> PaymentLinkCreated:
        """Создаёт платёжную ссылку. ``POST /v1/payment/link``.

        Поля: ``amount_mode`` (``fixed|open|range``), ``currency``, ``amount_fixed``/
        ``amount_min``/``amount_max``, ``pinned_currency``/``pinned_network``, ``title``,
        ``description``, ``expires_in`` (секунды; 0 — бессрочно).

        Имена полей проверяются по белому списку
        (:data:`oblodai._params.PAYMENT_LINK_FIELDS`): неизвестное имя — ``TypeError``.
        Management-эндпоинт не двигает деньги, поэтому ``idempotency_key`` здесь не
        принимается.
        """
        check_params("payment_links.create", params, PAYMENT_LINK_FIELDS, allow_idempotency_key=False)
        return PaymentLinkCreated.model_validate(self._http.request("/v1/payment/link", params))

    def list(self, *, limit: Optional[int] = None, offset: Optional[int] = None) -> List[PaymentLink]:
        data = self._http.request("/v1/payment/link/list", _clean(limit=limit, offset=offset))
        return [PaymentLink.model_validate(x) for x in data.get("items", [])]

    def info(self, link_id: str) -> PaymentLinkInfo:
        """Ссылка + платежи по ней. ``POST /v1/payment/link/info``."""
        return PaymentLinkInfo.model_validate(self._http.request("/v1/payment/link/info", {"link_id": link_id}))

    def toggle(self, link_id: str, active: bool) -> Dict[str, Any]:
        return self._http.request("/v1/payment/link/toggle", {"link_id": link_id, "active": active})

    def public_get(self, link_id: str) -> Any:
        """Публичные данные ссылки (без подписи). ``GET /v1/link/{id}``."""
        return self._http.request_public(f"/v1/link/{link_id}", method="GET")

    def checkout(self, link_id: str, **params: Any) -> Payment:
        """Публичный checkout по ссылке (без подписи). ``POST /v1/link/{id}/checkout``.

        Поля: ``amount``, ``currency``, ``network``, ``payer_email``. Закреплённые на ссылке
        валюта/сеть побеждают. Лимит: 30 инвойсов/мин на ссылку. Ответ — обычный платёж.
        """
        return Payment.model_validate(self._http.request_public(f"/v1/link/{link_id}/checkout", params))


class Splits(_Base):
    """Сплит-платежи: доля каждого входящего платежа автоматически уходит партнёру."""

    def create_rule(self, **params: Any) -> SplitRuleCreated:
        """Создаёт правило сплита. ``POST /v1/split/rule``.

        Либо ``address`` + ``network`` (внешний адрес, необратимо), либо ``merchant_id``
        (аккаунт на платформе, обратимо) — ровно одно из двух. ``percent`` — доля в процентах
        (шаг 0.01), ``note`` — заметка.

        Имена полей проверяются по белому списку
        (:data:`oblodai._params.SPLIT_RULE_FIELDS`): неизвестное имя — ``TypeError``
        (опечатка в ``percent`` увела бы долю партнёра в 0). Допустимые поля: ``address``,
        ``network``, ``merchant_id``, ``percent``, ``note``.
        """
        check_params("splits.create_rule", params, SPLIT_RULE_FIELDS, allow_idempotency_key=False)
        return SplitRuleCreated.model_validate(self._http.request("/v1/split/rule", params))

    def split_to_address(
        self, *, address: str, network: str, percent: float, note: Optional[str] = None
    ) -> SplitRuleCreated:
        """Правило «доля на внешний адрес» (необратимо при возвратах). Обёртка над :meth:`create_rule`."""
        return self.create_rule(**_clean(address=address, network=network, percent=percent, note=note))

    def split_to_merchant(self, *, merchant_id: str, percent: float, note: Optional[str] = None) -> SplitRuleCreated:
        """Правило «доля аккаунту на платформе» (обратимо: возврат отзовёт долю). Обёртка над :meth:`create_rule`."""
        return self.create_rule(**_clean(merchant_id=merchant_id, percent=percent, note=note))

    def list_rules(self) -> List[SplitRule]:
        data = self._http.request("/v1/split/rule/list", {})
        return [SplitRule.model_validate(x) for x in data.get("items", [])]

    def delete_rule(self, rule_id: str) -> Dict[str, Any]:
        return self._http.request("/v1/split/rule/delete", {"rule_id": rule_id})

    def get_config(self) -> Dict[str, Any]:
        return self._http.request("/v1/split/config/get", {})

    def set_config(self, *, refund_hold_hours: int) -> Dict[str, Any]:
        """Окно удержания перед отправкой долей (часы) — защита базы возвратов. ``POST /v1/split/config/set``."""
        return self._http.request("/v1/split/config/set", {"refund_hold_hours": refund_hold_hours})


class PayoutLinks(_Base):
    """Payout-ссылки («крипто-чеки»): резервируете сумму, получатель сам вводит адрес на странице claim.

    Создание ссылки РЕЗЕРВИРУЕТ баланс, поэтому SDK шлёт на ``/v1/payout/link`` и
    ``/v1/payout/link/batch`` заголовок ``Idempotency-Key`` — он вычисляется ОДИН раз до
    цикла ретраев, так что автоматический повтор после таймаута уходит с тем же ключом.

    Шлюз этот заголовок УВАЖАЕТ (оба маршрута обёрнуты в idempotency-middleware): повтор с
    тем же ключом реплеит первый ответ (та же ссылка, тот же ``claim_token``, заголовок
    ответа ``Idempotent-Replayed: true``), а баланс дебетуется РОВНО ОДИН РАЗ. Без
    заголовка два одинаковых вызова создадут ДВЕ ссылки. Возможные ответы шлюза:

    * 400 ``idempotency.key_reused`` — тот же ключ с ДРУГИМ телом;
    * 400 ``idempotency.bad_key`` — ключ длиннее 255 символов;
    * 409 ``idempotency.in_progress`` — параллельный повтор, пока первый ещё выполняется;
    * 503 ``idempotency.unavailable`` — стор идемпотентности недоступен (fail-closed),
      единственный из перечисленных, который SDK повторяет автоматически;
    * 409 ``payoutlink.duplicate_reference`` — ``reference`` уже занят (раньше было 500).

    Per-link ``reference`` (уникален в рамках мерчанта) — второй, durable слой защиты:
    он работает и без заголовка, и когда ответ батча слишком велик для кэша (>256 КБ).
    Требуют PAYOUT/API-ключ.
    """

    def create(self, **params: Any) -> PayoutLinkCreated:
        """Создаёт claimable-ссылку (резервирует средства). ``POST /v1/payout/link``.

        Поля: ``currency``, ``network``, ``amount`` (обязательные), ``reference`` (ключ
        дедупликации), ``title``, ``note``, ``email`` (получателю уйдёт claim-письмо),
        ``expires_in_hours``.

        Рекомендуем задавать ``expires_in_hours`` ЯВНО (1–720): при отсутствии или ``0``
        бэкенд клампит срок к 1 часу, а не к максимуму. ``claim_token``/``claim_url``
        возвращаются только этим вызовом — сохраните их сразу.

        Вызов резервирует средства, поэтому идёт с заголовком ``Idempotency-Key``
        (авто-uuid4, одинаков во всех внутренних ретраях; свой — kwarg ``idempotency_key``,
        в тело запроса он не попадает). Шлюз его уважает: повтор с тем же ключом реплеит
        первый ответ и не резервирует баланс второй раз. Дубль ``reference`` — 409
        ``payoutlink.duplicate_reference``.

        Имена полей проверяются по белому списку
        (:data:`oblodai._params.PAYOUT_LINK_FIELDS`): неизвестное имя — ``TypeError``.
        Допустимые поля: ``currency``, ``network``, ``amount``, ``reference``, ``title``,
        ``note``, ``email``, ``expires_in_hours`` (плюс SDK-kwarg ``idempotency_key``).
        Внимание на ``expires_in_hours``: опечатка тут не отбивалась и давала срок 1 час.
        """
        check_params("payout_links.create", params, PAYOUT_LINK_FIELDS)
        key = _pop_idem_key(params)
        return PayoutLinkCreated.model_validate(
            self._http.request("/v1/payout/link", params, idempotency_key=key)
        )

    def create_batch(
        self, links: List[Dict[str, Any]], *, idempotency_key: Optional[str] = None
    ) -> PayoutLinkBatchResult:
        """Пачка ссылок (до 500) одним запросом. ``POST /v1/payout/link/batch``.

        Каждый item — тело обычного ``create`` (тоже рекомендуем явный ``expires_in_hours``);
        все ссылки вызова получают общий ``batch_id``. Ответ index-aligned: плохой item фейлит
        только себя. Пачка резервирует средства, поэтому идёт с заголовком
        ``Idempotency-Key`` (авто-uuid4, стабилен между ретраями; свой — ``idempotency_key``),
        и шлюз его уважает.

        Две особенности батча:

        * частично упавшая пачка реплеится КАК ЕСТЬ — упавшие элементы под тем же ключом
          НЕ переисполняются, шлите их НОВЫМ ключом;
        * ответ больше 256 КБ шлюз не кэширует, и тогда повтор выполнится заново — поэтому
          на батчах ОБЯЗАТЕЛЬНО проставляйте per-item ``reference`` (второй слой защиты,
          дубль отбивается как 409 ``payoutlink.duplicate_reference``).
        """
        return PayoutLinkBatchResult.model_validate(
            self._http.request(
                "/v1/payout/link/batch", {"links": links}, idempotency_key=_idem_key(idempotency_key)
            )
        )

    def list(self, *, limit: Optional[int] = None, offset: Optional[int] = None) -> List[PayoutLink]:
        data = self._http.request("/v1/payout/link/list", _clean(limit=limit, offset=offset))
        return [PayoutLink.model_validate(x) for x in data.get("links", [])]

    def info(self, link_id: str) -> PayoutLink:
        """Состояние ссылки (после claim содержит ``payout_id`` и ``claim_address``). ``POST /v1/payout/link/info``."""
        return PayoutLink.model_validate(self._http.request("/v1/payout/link/info", {"link_id": link_id}))

    def cancel(self, link_id: str) -> PayoutLink:
        """Отменяет непорученную (``funded``) ссылку и возвращает резерв. ``POST /v1/payout/link/cancel``."""
        return PayoutLink.model_validate(self._http.request("/v1/payout/link/cancel", {"link_id": link_id}))

    def claim_info(self, token: str) -> PayoutLinkClaimInfo:
        """ПУБЛИЧНО (без подписи): данные ссылки для страницы claim. ``GET /v1/claim/{token}``."""
        return PayoutLinkClaimInfo.model_validate(self._http.request_public(f"/v1/claim/{token}", method="GET"))

    def claim(self, token: str, *, address: str, memo: Optional[str] = None) -> PayoutLinkClaimResult:
        """ПУБЛИЧНО (без подписи): забрать средства на ``address``. ``POST /v1/claim/{token}``.

        ``memo`` — dest tag/comment для сетей, где он нужен (TON и т. п.). Повторный claim с
        тем же адресом — идемпотентный успех; с другим адресом — ``payoutlink.claim_in_progress``.
        """
        body: Dict[str, Any] = {"address": address}
        if memo is not None:
            body["memo"] = memo
        return PayoutLinkClaimResult.model_validate(self._http.request_public(f"/v1/claim/{token}", body))


class Wallets(_Base):
    def create(self, **params: Any) -> Wallet:
        return Wallet.model_validate(self._http.request("/v1/wallet", params))

    def block(self, *, address: str, is_force_block: Optional[bool] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"address": address}
        if is_force_block is not None:
            body["is_force_block"] = is_force_block
        return self._http.request("/v1/wallet/block", body)

    def blocked_address_refund(
        self, *, uuid: str, address: str, idempotency_key: Optional[str] = None
    ) -> Any:
        """Возврат с заблокированного адреса. ``POST /v1/wallet/blocked-address-refund``.

        Once-only на уровне САМОГО шлюза, безусловно и без всяких заголовков: обработчик
        строит детерминированный reference ``refund-wallet:<wallet_id>``, берёт per-wallet
        advisory-lock и внутри лока возвращает УЖЕ СОЗДАННУЮ выплату, если она есть.
        Повтор (в том числе параллельный) отдаёт ТУ ЖЕ выплату, вторая не создаётся.
        Оговорка: повтор с ДРУГИМ ``address`` вернёт первую выплату на ПЕРВЫЙ адрес —
        адрес в reference не входит.

        Этот маршрут НЕ обёрнут в idempotency-middleware шлюза (намеренно: обёртка отдавала
        бы конкурентному повтору 409 вместо ожидания и успеха), так что ``Idempotency-Key``
        здесь шлётся, но серверу не нужен — защита выше него. Свой ключ — kwarg
        ``idempotency_key``.
        """
        return self._http.request(
            "/v1/wallet/blocked-address-refund",
            {"uuid": uuid, "address": address},
            idempotency_key=_idem_key(idempotency_key),
        )

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
        """Перевод на персональный счёт. ``POST /v1/transfer/to-personal``.

        Идемпотентность (v1.1.0): заголовок ``Idempotency-Key`` — авто-uuid4, одинаков во
        всех внутренних ретраях; свой ключ — kwarg ``idempotency_key``. ``order_id`` больше
        НЕ подставляется автоматически.
        """
        key = _pop_idem_key(params)
        return self._http.request("/v1/transfer/to-personal", params, idempotency_key=key)

    def transfer_to_user(
        self,
        *,
        to_user_id: str,
        amount: str,
        currency: str,
        order_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> TransferToUserResult:
        """Внутренний перевод БЕЗ комиссии с баланса мерчанта на личный кошелёк
        пользователя платформы. ``POST /v1/transfer/to-user`` (PAYOUT/API-ключ).

        ``to_user_id`` — id пользователя платформы (UUID-строка), НЕ username: username
        резолвится в id через публичный профиль кабинета. Идемпотентность — та же
        лестница, что у остальных денежных эндпоинтов: заголовок ``Idempotency-Key``
        (SDK шлёт авто-uuid4, стабильный между ретраями; свой — ``idempotency_key``),
        иначе шлюз берёт ``order_id``, иначе — подпись запроса.
        """
        body = _clean(to_user_id=to_user_id, amount=amount, currency=currency, order_id=order_id)
        return TransferToUserResult.model_validate(
            self._http.request("/v1/transfer/to-user", body, idempotency_key=_idem_key(idempotency_key))
        )

    def transfer_batch(
        self,
        transfers: List[Dict[str, Any]],
        *,
        on_error: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> BatchSubmitResult:
        """Ставит пачку внутренних переводов to-user (до 5000). ``POST /v1/transfer/batch``.

        Каждый item — тело обычного :meth:`transfer_to_user` (``to_user_id``, ``amount``,
        ``currency``, опционально ``order_id``). ``on_error`` — ``"continue"``
        (по умолчанию) или ``"stop"``. Обработка в фоне: прогресс и по-элементные
        результаты — через ``client.batches.info(batch_id)``. Идемпотентность —
        заголовком ``Idempotency-Key`` (авто-uuid4; свой — ``idempotency_key``).
        """
        body: Dict[str, Any] = {"transfers": transfers}
        if on_error is not None:
            body["on_error"] = on_error
        return BatchSubmitResult.model_validate(
            self._http.request("/v1/transfer/batch", body, idempotency_key=_idem_key(idempotency_key))
        )

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


class Sandbox(_Base):
    """Песочница разработчика — ТОЛЬКО для тестовых ключей (``test_…`` / ``oblodai_test_…``).

    Пять test-only эндпоинтов, заменяющих действия, которые в проде совершает покупатель
    (он-чейн оплата и т. п.). Бизнес-эндпоинты с тестовым ключом работают БЕЗ изменений —
    между тестом и продом меняется только ключ. Живой ключ на этих эндпоинтах получает
    HTTP 403 ``sandbox.live_key``. Не используйте эту группу в продакшн-коде.
    """

    def simulate_deposit(
        self,
        *,
        invoice_id: str,
        amount: Optional[str] = None,
        confirmations: Optional[int] = None,
        txid: Optional[str] = None,
    ) -> SandboxDeposit:
        """Имитирует он-чейн депозит в инвойс. ``POST /v1/sandbox/deposit``.

        ``amount`` не задан — оплачивается ровно причитающееся; другое значение даёт
        недоплату/переплату. ``confirmations`` не задан/0 — депозит сразу полностью
        подтверждён; малое число — приходит «в пути»; повтор с ТЕМ ЖЕ ``txid`` и бОльшим
        числом подтверждений «углубляет» его. ``txid`` не задан — свежий; переиспользуйте
        для теста идемпотентности/углубления.
        """
        body = _clean(invoice_id=invoice_id, amount=amount, confirmations=confirmations, txid=txid)
        return SandboxDeposit.model_validate(self._http.request("/v1/sandbox/deposit", body))

    def faucet(
        self, *, asset: str, amount: str, idempotency_key: Optional[str] = None
    ) -> SandboxFaucetResult:
        """Начисляет тестовый баланс (кран), чтобы гонять выплаты/возвраты.
        ``POST /v1/sandbox/faucet``.

        ``amount`` ограничен 1000000 за вызов. ``idempotency_key`` здесь — поле ТЕЛА
        запроса (так определено контрактом эндпоинта), а не заголовок ``Idempotency-Key``.
        """
        body = _clean(asset=asset, amount=amount, idempotency_key=idempotency_key)
        return SandboxFaucetResult.model_validate(self._http.request("/v1/sandbox/faucet", body))

    def reset(self) -> SandboxResetResult:
        """Отменяет открытые инвойсы и обнуляет балансы (компенсирующая проводка,
        история сохраняется). ``POST /v1/sandbox/reset``."""
        return SandboxResetResult.model_validate(self._http.request("/v1/sandbox/reset", {}))

    def list_webhooks(self) -> List[SandboxDelivery]:
        """Недавние доставки вебхуков (до 50, новые первыми). ``GET /v1/sandbox/webhooks``.

        Подписанный GET с ПУСТЫМ телом: каноническая строка —
        ``{ts}\\nGET\\n/v1/sandbox/webhooks\\n`` (пустое тело после последнего ``\\n``).
        """
        data = self._http.request("/v1/sandbox/webhooks", method="GET")
        return [SandboxDelivery.model_validate(x) for x in data.get("deliveries", [])]

    def replay_webhook(self, delivery_id: str) -> SandboxReplayResult:
        """Перепоставляет одну доставку в очередь. ``POST /v1/sandbox/webhooks/replay``."""
        return SandboxReplayResult.model_validate(
            self._http.request("/v1/sandbox/webhooks/replay", {"delivery_id": delivery_id})
        )


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


def _idem_key(explicit: Optional[str] = None) -> str:
    """Ключ идемпотентности для заголовка ``Idempotency-Key`` (v1.1.0).

    Если вызывающий передал непустой свой ключ — используется он, иначе генерируется uuid4.
    Вызывается ОДИН раз на вызов метода (до цикла ретраев), поэтому все внутренние повторы
    уходят с одним и тем же ключом. В подпись запроса заголовок не входит.
    """
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    return str(_uuid.uuid4())


def _pop_idem_key(params: Dict[str, Any]) -> str:
    """Достаёт caller-ключ ``idempotency_key`` из kwargs (УДАЛЯЯ его из тела запроса —
    иначе он утёк бы в подписанное тело) и возвращает итоговый ключ для заголовка."""
    return _idem_key(params.pop("idempotency_key", None))


def _lookup(uuid: Optional[str], order_id: Optional[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if uuid is not None:
        out["uuid"] = uuid
    if order_id is not None:
        out["order_id"] = order_id
    return out


def _clean(**kwargs: Any) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}
