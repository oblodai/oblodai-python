"""Official Python SDK for the Oblodai crypto payment gateway.

    from oblodai import Oblodai

    oblodai = Oblodai(public_id="pk_live_...", secret="...")
    invoice = oblodai.payments.create(
        {"amount": "25", "currency": "USDT", "network": "tron", "order_id": "order-1"}
    )
    print(invoice["url"])

Everything the gateway declares is shipped as data in ``contract/`` and mirrored here: routes,
enums, request bodies and response models. Amounts are decimal strings; field names are exactly
the wire's snake_case.
"""

from __future__ import annotations

from ._version import SDK_VERSION
from .aio import AsyncOblodai
from .client import Oblodai
from .config import DEFAULT_BASE_URL, resolve_config
from .contract.enums import (
    DELIVERY_STATUSES,
    ERROR_CODES,
    EVENT_TYPES,
    NETWORKS,
    PAYMENT_STATUSES,
    PAYOUT_LINK_STATUSES,
    PAYOUT_STATUSES,
    DeliveryStatus,
    ErrorCode,
    EventType,
    FeeBearer,
    FeeBearerResult,
    Network,
    PaymentStatus,
    PayoutLinkStatus,
    PayoutStatus,
    WebhookKind,
)
from .contract.models import *  # noqa: F403  - every response model
from .contract.models import __all__ as _models_all
from .contract.routes import ROUTE_KEYS, ROUTES
from .contract.types import RouteAuth, RouteSpec
from .contract.version import CONTRACT_CORE_COMMIT, CONTRACT_EXPORTED_AT, CONTRACT_HASH
from .core.errors import (
    ApiError,
    AuthenticationError,
    ConfigError,
    ConflictError,
    ContractError,
    IdempotencyConflictError,
    InternalError,
    NotFoundError,
    OblodaiError,
    PermissionError,
    RateLimitError,
    SignatureError,
    TransportError,
    UnavailableError,
    ValidationError,
)
from .core.idempotency import new_idempotency_key
from .core.pagination import AsyncPage, Page, PageResult
from .core.retry import RetryOptions
from .core.signing import canonical_string, sign_request, sign_webhook
from .helpers import (
    FINAL_PAYMENT_STATUSES,
    FINAL_PAYOUT_STATUSES,
    add_amounts,
    amount_equals,
    compare_amounts,
    is_payment_final,
    is_payment_paid,
    is_payment_underpaid,
    is_payout_final,
    is_payout_succeeded,
    is_zero_amount,
    subtract_amounts,
)
from .resources import FileResult
from .webhooks import WebhookDeliveryInfo, is_test_event

# Webhook verification also lives in `oblodai.webhooks` and needs no client.
from .webhooks import is_stale as verify_is_stale
from .webhooks import parse as parse_webhook
from .webhooks import verify as verify_webhook
from .webhooks import verify_delivery as verify_webhook_delivery

_model_names = _models_all

__all__ = [
    "CONTRACT_CORE_COMMIT",
    "CONTRACT_EXPORTED_AT",
    "CONTRACT_HASH",
    "DEFAULT_BASE_URL",
    "DELIVERY_STATUSES",
    "ERROR_CODES",
    "EVENT_TYPES",
    "FINAL_PAYMENT_STATUSES",
    "FINAL_PAYOUT_STATUSES",
    "NETWORKS",
    "PAYMENT_STATUSES",
    "PAYOUT_LINK_STATUSES",
    "PAYOUT_STATUSES",
    "ROUTES",
    "ROUTE_KEYS",
    "SDK_VERSION",
    "ApiError",
    "AsyncOblodai",
    "AsyncPage",
    "AuthenticationError",
    "ConfigError",
    "ConflictError",
    "ContractError",
    "DeliveryStatus",
    "ErrorCode",
    "EventType",
    "FeeBearer",
    "FeeBearerResult",
    "FileResult",
    "IdempotencyConflictError",
    "InternalError",
    "Network",
    "NotFoundError",
    "Oblodai",
    "OblodaiError",
    "Page",
    "PageResult",
    "PaymentStatus",
    "PayoutLinkStatus",
    "PayoutStatus",
    "PermissionError",
    "RateLimitError",
    "RetryOptions",
    "RouteAuth",
    "RouteSpec",
    "SignatureError",
    "TransportError",
    "UnavailableError",
    "ValidationError",
    "WebhookDeliveryInfo",
    "WebhookKind",
    "add_amounts",
    "amount_equals",
    "canonical_string",
    "compare_amounts",
    "is_payment_final",
    "is_payment_paid",
    "is_payment_underpaid",
    "is_payout_final",
    "is_payout_succeeded",
    "is_test_event",
    "is_zero_amount",
    "new_idempotency_key",
    "parse_webhook",
    "resolve_config",
    "sign_request",
    "sign_webhook",
    "subtract_amounts",
    "verify_is_stale",
    "verify_webhook",
    "verify_webhook_delivery",
    *_model_names,
]
