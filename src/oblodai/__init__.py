"""Official Python SDK for the Oblodai crypto payment gateway.

    from oblodai import Oblodai

    oblodai = Oblodai(public_id="pk_live_...", secret="...")
    invoice = oblodai.payments.create(
        {"amount": "25", "currency": "USDT", "network": "tron", "order_id": "order-1"}
    )
    print(invoice.url)

Routes, enums, models and resource methods are generated from the gateway's OpenAPI document
(:mod:`oblodai.generated`) and exported here. Amounts are decimal strings or ``Decimal``; field
names are exactly the wire's snake_case.
"""

from __future__ import annotations

from ._version import SDK_VERSION
from .aio import AsyncOblodai
from .client import Oblodai
from .config import DEFAULT_BASE_URL, resolve_config
from .contract.version import CONTRACT_CORE_COMMIT, CONTRACT_EXPORTED_AT, CONTRACT_HASH
from .core.errors import (
    AmountError,
    ApiError,
    AuthenticationError,
    ConfigError,
    ConflictError,
    ContractError,
    IdempotencyConflictError,
    InternalError,
    NotFoundError,
    OblodaiError,
    PermissionDeniedError,
    RateLimitError,
    ResponseTooLargeError,
    SignatureError,
    TransportError,
    UnavailableError,
    ValidationError,
    WebhookPayloadError,
)
from .core.hooks import Hooks, RequestInfo, ResponseInfo
from .core.idempotency import new_idempotency_key
from .core.options import RequestOptions
from .core.pagination import AsyncPage, Page, PageResult
from .core.poller import AsyncJob, Job
from .core.raw import RawAPIResponse
from .core.retry import RetryOptions
from .core.route import RouteAuth, RouteSpec
from .core.signing import canonical_string, sign_request, sign_webhook
from .generated import enums as _generated_enums
from .generated import models as _generated_models
from .generated.enums import *  # noqa: F403  - every enumeration of the API
from .generated.models import *  # noqa: F403  - every model of the API
from .generated.routes import ROUTES
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
from .webhooks import WebhookDeliveryInfo, is_known_event, is_test_event

# Webhook verification also lives in `oblodai.webhooks` and needs no client.
from .webhooks import is_stale as verify_is_stale
from .webhooks import parse as parse_webhook
from .webhooks import verify as verify_webhook
from .webhooks import verify_delivery as verify_webhook_delivery

_generated_names = sorted(
    name
    for module in (_generated_enums, _generated_models)
    for name, value in vars(module).items()
    if getattr(value, "__module__", None) == module.__name__ and not name.startswith("_")
)

#: PEP 396 spelling of :data:`SDK_VERSION`, for tools that look for it.
__version__ = SDK_VERSION

__all__ = [
    "CONTRACT_CORE_COMMIT",
    "CONTRACT_EXPORTED_AT",
    "CONTRACT_HASH",
    "DEFAULT_BASE_URL",
    "FINAL_PAYMENT_STATUSES",
    "FINAL_PAYOUT_STATUSES",
    "ROUTES",
    "SDK_VERSION",
    "__version__",
    "AmountError",
    "ApiError",
    "AsyncOblodai",
    "AsyncPage",
    "AuthenticationError",
    "ConfigError",
    "ConflictError",
    "ContractError",
    "FileResult",
    "IdempotencyConflictError",
    "InternalError",
    "NotFoundError",
    "Oblodai",
    "OblodaiError",
    "Page",
    "PageResult",
    "Job",
    "AsyncJob",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestOptions",
    "Hooks",
    "RequestInfo",
    "ResponseInfo",
    "RawAPIResponse",
    "ResponseTooLargeError",
    "RetryOptions",
    "RouteAuth",
    "RouteSpec",
    "SignatureError",
    "TransportError",
    "UnavailableError",
    "ValidationError",
    "WebhookDeliveryInfo",
    "WebhookPayloadError",
    "add_amounts",
    "amount_equals",
    "canonical_string",
    "compare_amounts",
    "is_payment_final",
    "is_payment_paid",
    "is_payment_underpaid",
    "is_payout_final",
    "is_payout_succeeded",
    "is_known_event",
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
    *_generated_names,
]
