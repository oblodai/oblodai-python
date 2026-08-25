"""Error model.

One family, :class:`OblodaiError`, mirrors the core's error envelope::

    {"error": {"code", "message", "field"?, "retryable", "retry_after"?, "request_id"?}}

``retryable`` is authoritative when the core wrote the envelope: it is the core's own
classification of the failure. A response without an envelope (a proxy 502, an HTML 503) is
``synthetic`` - the core never saw or never answered the request - and is retried only when
repeating is safe. Subclasses exist for ``except`` ergonomics; the discriminator is always ``code``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict

__all__ = [
    "TRANSIENT_STATUSES",
    "ApiError",
    "AuthenticationError",
    "ConfigError",
    "ConflictError",
    "ContractError",
    "ErrorDetail",
    "IdempotencyConflictError",
    "InternalError",
    "NotFoundError",
    "OblodaiError",
    "PermissionError",
    "RateLimitError",
    "SignatureError",
    "TransportError",
    "UnavailableError",
    "ValidationError",
    "api_error_from",
]


class ErrorDetail(TypedDict, total=False):
    """The ``error`` object of the core's failure envelope."""

    code: str
    message: str
    field: str
    retryable: bool
    retry_after: int
    request_id: str


class OblodaiError(Exception):
    """Base class of everything this SDK raises."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int = 0,
        retryable: bool = False,
        retry_after: Optional[float] = None,
        request_id: Optional[str] = None,
        field: Optional[str] = None,
        synthetic: bool = False,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        #: Stable machine code (``family.reason``), e.g. ``payout.insufficient_funds``.
        self.code = code
        self.message = message
        #: HTTP status, or 0 when no response was received.
        self.http_status = http_status
        #: Whether repeating the identical request can succeed later.
        self.retryable = retryable
        #: Seconds to wait before retrying, when the core (or a ``Retry-After``) gave a hint.
        self.retry_after = retry_after
        #: Server-side request id - quote it when contacting support.
        self.request_id = request_id
        #: The request field the error refers to, for validation failures.
        self.field = field
        #: No core envelope: the answer came from something in front of the core.
        self.synthetic = synthetic
        # Deliberately not part of __repr__/to_dict: a raw body may hold merchant data.
        self.raw = raw

    @property
    def family(self) -> str:
        """Code family (``payout`` in ``payout.insufficient_funds``)."""
        head, _, _ = self.code.partition(".")
        return head

    def to_dict(self) -> Dict[str, Any]:
        """Structured-logger friendly: keeps the message, drops the raw body."""
        return {
            "name": type(self).__name__,
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
            "retryable": self.retryable,
            "retry_after": self.retry_after,
            "request_id": self.request_id,
            "field": self.field,
            "synthetic": self.synthetic,
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code!r}, http_status={self.http_status}, "
            f"retryable={self.retryable}, message={self.message!r})"
        )


class TransportError(OblodaiError):
    """The request never produced an HTTP response: DNS, TCP, TLS, timeout, abort, deadline."""

    def __init__(self, code: str, message: str, cause: Optional[BaseException] = None) -> None:
        super().__init__(
            code,
            message,
            http_status=0,
            retryable=code in ("transport.timeout", "transport.network"),
        )
        self.__cause__ = cause


class ConfigError(OblodaiError):
    """Raised before any request is sent: bad options, missing credentials, unusable arguments."""

    def __init__(self, code: str, message: str, field: Optional[str] = None) -> None:
        super().__init__(code, message, http_status=0, retryable=False, field=field)


class ApiError(OblodaiError):
    """The core (or something in front of it) answered with an error status."""


class ValidationError(ApiError):
    """400 - the request is malformed or violates a business rule; see ``field`` and ``code``."""


class AuthenticationError(ApiError):
    """401 - bad signature, unknown key, clock skew, IP not in the allow-list."""


class PermissionError(ApiError):
    """403 - the key is valid but not allowed to do this (wrong key kind, feature disabled)."""


class NotFoundError(ApiError):
    """404 - the referenced object does not exist for this merchant."""


class ConflictError(ApiError):
    """409 - state or idempotency conflict."""


class IdempotencyConflictError(ConflictError):
    """409 ``idempotency.key_reused`` - the same key was used with a different request body."""


class RateLimitError(ApiError):
    """429 - rate limited; ``retry_after`` is set."""


class UnavailableError(ApiError):
    """503 - an upstream dependency is down; safe to retry after a pause."""


class InternalError(ApiError):
    """5xx other than 503."""


class ContractError(OblodaiError):
    """The response could not be interpreted as the documented envelope."""

    def __init__(self, message: str, http_status: int, raw: Any = None) -> None:
        super().__init__(
            "sdk.bad_envelope", message, http_status=http_status, retryable=False, raw=raw
        )


class SignatureError(OblodaiError):
    """Webhook verification failed (bad signature, stale timestamp, missing headers)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, http_status=0, retryable=False)


#: Statuses a response without an envelope may carry transiently (LB/proxy/timeouts).
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def api_error_from(
    http_status: int,
    detail: ErrorDetail,
    raw: Any = None,
    *,
    synthetic: bool = False,
    retry_after_header: Optional[float] = None,
) -> ApiError:
    """Build the right subclass from an error envelope (or a synthesized one) and the status."""
    code = detail.get("code") or "internal"
    message = detail.get("message") or (
        f"request failed with HTTP {http_status} ({detail.get('code') or 'no envelope'})"
    )
    if synthetic:
        retryable = http_status in TRANSIENT_STATUSES
    else:
        declared = detail.get("retryable")
        retryable = declared if declared is not None else http_status in (429, 503)
    body_retry_after = detail.get("retry_after")
    kwargs: Dict[str, Any] = {
        "http_status": http_status,
        "retryable": retryable,
        "retry_after": body_retry_after if body_retry_after is not None else retry_after_header,
        "request_id": detail.get("request_id"),
        "field": detail.get("field"),
        "synthetic": synthetic,
        "raw": raw,
    }
    if code == "idempotency.key_reused":
        return IdempotencyConflictError(code, message, **kwargs)
    by_status = {
        400: ValidationError,
        401: AuthenticationError,
        403: PermissionError,
        404: NotFoundError,
        409: ConflictError,
        429: RateLimitError,
        503: UnavailableError,
    }
    cls = by_status.get(http_status)
    if cls is None:
        cls = InternalError if http_status >= 500 else ApiError
    return cls(code, message, **kwargs)
