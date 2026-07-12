"""Pydantic-модели объектов API.

Суммы — строки в единицах валюты (``"25.00"``), не числа, — чтобы не терять точность. Модели
настроены игнорировать неописанные поля (``extra="ignore"``): API может вернуть дополнительные поля,
и это не должно ломать разбор.
"""

from __future__ import annotations

from typing import Dict, List, Optional

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
