"""Pydantic-модели объектов API.

Суммы — строки в единицах валюты (``"25.00"``), не числа, — чтобы не терять точность. Модели
настроены игнорировать неописанные поля (``extra="ignore"``): API может вернуть дополнительные поля,
и это не должно ломать разбор.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ─────────────────────────────── Платежи ───────────────────────────────


class Payment(_Model):
    uuid: str
    order_id: str
    amount: str
    payment_amount: Optional[str] = None
    amount_paid: Optional[str] = None
    amount_remaining: Optional[str] = None
    payer_amount: Optional[str] = None
    payer_currency: Optional[str] = None
    currency: str
    network: Optional[str] = None
    address: Optional[str] = None
    address_qr_code: Optional[str] = None
    payment_status: str
    is_multi: bool = False
    url: Optional[str] = None
    expired_at: Optional[int] = None
    is_final: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    additional_data: Optional[str] = None
    payer_email: Optional[str] = None
    url_return: Optional[str] = None
    url_success: Optional[str] = None
    rate_expires_at: Optional[int] = None
    confirmations: Optional[int] = None
    required_confirmations: Optional[int] = None
    txid: Optional[str] = None
    # v1.1.0
    payer_address: Optional[str] = None
    refund_status: Optional[str] = None  # "none" | "partial" | "full"
    refunds: Optional[List[Dict[str, Any]]] = None
    # v1.2.0: только в публичном ``GET /v1/pay/{id}`` для валюто-агностичного инвойса в статусе
    # ``select`` — методы (валюта+сеть), из которых покупатель выбирает на странице оплаты.
    accepted: Optional[List["AcceptedMethod"]] = None


class Paginate(_Model):
    count: int
    per_page: int
    offset: int


class PaymentList(_Model):
    items: List[Payment]
    paginate: Paginate


class Limit(_Model):
    min_amount: str
    max_amount: str


class Commission(_Model):
    fee_amount: str
    percent: str


class ServiceMethod(_Model):
    network: str
    currency: str
    is_available: bool
    limit: Optional[Limit] = None
    commission: Optional[Commission] = None


# ─────────────────────────────── Кошельки ───────────────────────────────


class Wallet(_Model):
    uuid: str
    address: str
    network: str
    currency: str
    order_id: Optional[str] = None
    url: Optional[str] = None


class MerchantBalance(_Model):
    currency: str
    balance: str


class Balance(_Model):
    # Ответ вида { "balance": { "merchant": [ ... ] } }
    merchant: List[MerchantBalance]


class ReferralInfo(_Model):
    code: str
    link: str
    tier_bps: List[int]
    referred_count: int
    earnings_by_asset: Dict[str, str]


# ─────────────────────────────── Выплаты ───────────────────────────────


class PayoutConvert(_Model):
    from_currency: str
    to_currency: str
    from_amount: str
    rate: str


class Payout(_Model):
    uuid: str
    order_id: str
    amount: str
    currency: str
    network: Optional[str] = None
    address: str
    txid: Optional[str] = None
    status: str
    is_final: bool = False
    approval_required: bool = False
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    convert: Optional[PayoutConvert] = None


class MassPayoutItem(_Model):
    order_id: str
    success: bool
    uuid: Optional[str] = None
    status: Optional[str] = None
    is_final: Optional[bool] = None
    approval_required: Optional[bool] = None
    message: Optional[str] = None


class MassPayoutResult(_Model):
    items: List[MassPayoutItem]


class PayoutList(_Model):
    items: List[Payout]
    paginate: Paginate


class PayoutCalculation(_Model):
    amount: str
    currency: str
    network: Optional[str] = None
    commission: str
    merchant_amount: str
    to_amount: str


# ─────────────────────────────── Курсы ───────────────────────────────


class ExchangeRate(_Model):
    # В JSON поле называется "from" (зарезервированное слово в Python) — стандартный алиас pydantic.
    from_: str = Field(alias="from")
    to: str
    course: str

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CurrencyNetwork(_Model):
    """Сеть в публичном каталоге ``GET /v1/currencies``."""

    network: str
    kind: str  # "native" | "token"
    contract: Optional[str] = None
    min_confirmations: int
    available: bool  # синоним deposit_available
    deposit_available: bool
    payout_available: bool


class Currency(_Model):
    """Актив в публичном каталоге ``GET /v1/currencies``."""

    symbol: str
    decimals: int
    networks: List[CurrencyNetwork] = []


# ─────────────────────────────── Батчи (v1.1.0) ───────────────────────────────


class BatchSubmitResult(_Model):
    """Ответ постановки пачки (``/v1/payment|refund|payout/batch``)."""

    batch_id: str
    kind: str  # "payments" | "refunds" | "payouts"
    count: int
    status: str  # "pending"


class BatchItem(_Model):
    idx: int
    status: str
    order_id: Optional[str] = None
    result: Optional[Any] = None  # байт-в-байт result соответствующего единичного эндпоинта
    error: Optional[str] = None


class BatchInfo(_Model):
    batch_id: str
    kind: str
    status: str  # "pending" | "processing" | "completed"
    on_error: Optional[str] = None
    total: int
    succeeded: int
    failed: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[BatchItem] = []

    @property
    def done(self) -> bool:
        """``True``, когда пачка обработана до конца (``status == "completed"``)."""
        return self.status == "completed"


# ─────────────────────────────── Платёжные ссылки (v1.1.0) ───────────────────────────────


class PaymentLinkCreated(_Model):
    """Ответ ``POST /v1/payment/link``."""

    link_id: str
    url: Optional[str] = None


class PaymentLink(_Model):
    link_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    amount_mode: str  # "fixed" | "open" | "range"
    currency: str
    active: bool
    url: Optional[str] = None
    created_at: Optional[str] = None
    amount_fixed: Optional[str] = None
    amount_min: Optional[str] = None
    amount_max: Optional[str] = None
    pinned_currency: Optional[str] = None
    pinned_network: Optional[str] = None
    expires_at: Optional[str] = None


class PaymentLinkPayment(_Model):
    """Платёж в выдаче ``/v1/payment/link/info``."""

    uuid: str
    status: str
    amount: str
    currency: str
    created_at: Optional[str] = None
    order_id: Optional[str] = None


class PaymentLinkInfo(PaymentLink):
    payments: List[PaymentLinkPayment] = []


# ─────────────────────────────── Сплиты (v1.1.0) ───────────────────────────────


class SplitRuleCreated(_Model):
    rule_id: str
    percent: float


class SplitRule(_Model):
    rule_id: str
    percent: float
    active: bool
    note: Optional[str] = None
    # либо внешний адрес (необратимо), либо аккаунт на платформе (обратимо)
    address: Optional[str] = None
    network: Optional[str] = None
    merchant_id: Optional[str] = None
    reversible: Optional[bool] = None


# ─────────────────────────────── Payout-ссылки / крипто-чеки (v1.1.0) ───────────────────────────────


class PayoutLink(_Model):
    """Claimable-ссылка на выплату (``payoutLinkView``). Без claim-токена — он только в ответе create."""

    link_id: str
    status: str  # "funded" | "claiming" | "claimed" | "expired" | "cancelled"
    amount: str
    currency: str
    network: str
    title: Optional[str] = None
    note: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    reference: Optional[str] = None
    email: Optional[str] = None
    payout_id: Optional[str] = None
    claim_address: Optional[str] = None
    batch_id: Optional[str] = None


class PayoutLinkCreated(PayoutLink):
    """Ответ create: ``claim_token``/``claim_url`` возвращаются ЕДИНСТВЕННЫЙ раз — сохраните их."""

    claim_token: Optional[str] = None
    claim_url: Optional[str] = None


class PayoutLinkBatchItem(_Model):
    ok: bool
    link: Optional[PayoutLinkCreated] = None
    error: Optional[str] = None
    message: Optional[str] = None


class PayoutLinkBatchResult(_Model):
    created: int
    total: int
    results: List[PayoutLinkBatchItem] = []


class PayoutLinkClaimInfo(_Model):
    """Публичная информация о ссылке для страницы claim (``GET /v1/claim/{token}``)."""

    status: str
    amount: str
    currency: str
    network: str
    title: Optional[str] = None
    note: Optional[str] = None
    expires_at: Optional[str] = None
    claimable: bool = False


class PayoutLinkClaimResult(_Model):
    """Результат публичного claim (``POST /v1/claim/{token}``)."""

    status: str  # "claimed"
    payout_id: Optional[str] = None
    amount: str
    currency: str
    network: Optional[str] = None
    address: Optional[str] = None


# ─────────────────────────────── Resolve недоплаты (v1.1.0) ───────────────────────────────


class PaymentResolution(_Model):
    """Ответ ``POST /v1/payment/resolve``. Поля различаются по ``resolution``.

    ``resolution == "accepted"`` — заполнены ``amount_kept``/``currency``.
    ``resolution == "refunded"`` — заполнены ``uuid`` (рефанд-payout), ``amount``, ``address``,
    ``status`` (check/process/paid/fail/cancel) и ``is_final``.
    """

    payment_uuid: str
    order_id: Optional[str] = None
    resolution: str  # "accepted" | "refunded"
    currency: Optional[str] = None
    # accept
    amount_kept: Optional[str] = None
    # refund
    uuid: Optional[str] = None
    amount: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    is_final: Optional[bool] = None


# ─────────────────────────────── Внутренние переводы (v1.2.0) ───────────────────────────────


class TransferToUserResult(_Model):
    """Ответ ``POST /v1/transfer/to-user`` — внутренний перевод без комиссии
    на личный кошелёк пользователя платформы."""

    currency: str
    amount: str
    to_user_id: str
    recipient_balance: str


# ─────────────────────────────── Песочница (v1.2.0) ───────────────────────────────


class SandboxDeposit(_Model):
    """Ответ ``POST /v1/sandbox/deposit`` — сымитированный он-чейн депозит в инвойс."""

    invoice_id: str
    txid: str
    amount: str
    confirmations: int


class SandboxFaucetResult(_Model):
    """Ответ ``POST /v1/sandbox/faucet`` — начисление тестового баланса."""

    asset: str
    amount: str
    journal_id: str


class SandboxResetResult(_Model):
    """Ответ ``POST /v1/sandbox/reset``."""

    invoices_cancelled: int
    balances_zeroed: int


class SandboxDelivery(_Model):
    """Доставка вебхука в выдаче ``GET /v1/sandbox/webhooks`` (в отличие от
    :class:`Delivery` содержит ``payload`` — сырое тело вебхука)."""

    id: str
    event_type: str
    url: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    payload: Optional[Any] = None  # сырой JSON вебхука
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SandboxReplayResult(_Model):
    """Ответ ``POST /v1/sandbox/webhooks/replay``."""

    delivery_id: str
    requeued: bool


# ─────────────────────────────── Вебхуки/настройки ───────────────────────────────


class WebhookRegistration(_Model):
    endpoint_id: str
    url: str
    secret: str


class Delivery(_Model):
    id: str
    url: str
    event_type: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AcceptedMethod(_Model):
    currency: str
    network: str


class AutoWithdrawRule(_Model):
    currency: str
    network: str
    address: str
    min_minor: str
