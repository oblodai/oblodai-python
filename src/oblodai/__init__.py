"""Oblodai SDK — Python-клиент для платёжного шлюза Oblodai.

Синхронный и асинхронный клиенты, проверка вебхуков, типизированные ошибки и pydantic-модели.
"""

from __future__ import annotations

from ._transport import RetryConfig
from .client import AsyncOblodaiClient, OblodaiClient
from .errors import (
    OblodaiAPIError,
    OblodaiConnectionError,
    OblodaiError,
    OblodaiSignatureError,
    OblodaiTimeoutError,
)
from .signing import compute_webhook_signature, sign_request
from .webhooks import construct_event, verify_webhook

__version__ = "1.1.0"

__all__ = [
    "OblodaiClient",
    "AsyncOblodaiClient",
    "RetryConfig",
    # вебхуки
    "verify_webhook",
    "construct_event",
    # подпись
    "sign_request",
    "compute_webhook_signature",
    # ошибки
    "OblodaiError",
    "OblodaiAPIError",
    "OblodaiConnectionError",
    "OblodaiTimeoutError",
    "OblodaiSignatureError",
]
