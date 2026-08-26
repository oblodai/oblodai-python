"""Error model.

One family, :class:`OblodaiError`, mirrors the core's error envelope::

    {"error": {"code", "message", "field"?, "retryable", "retry_after"?, "request_id"?}}

``retryable`` is authoritative when the core wrote the envelope: it is the core's own
classification of the failure. A response without an envelope (a proxy 502, an HTML 503) is
``synthetic`` - the core never saw or never answered the request - and is retried only when
repeating is safe. Subclasses exist for ``except`` ergonomics; the discriminator is always ``code``.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, TypedDict

__all__ = [
    "MAX_RETRY_AFTER_SECONDS",
    "TRANSIENT_STATUSES",
    "AmountError",
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
    "PermissionDeniedError",
    "RateLimitError",
    "ResponseTooLargeError",
    "SignatureError",
    "TransportError",
    "UnavailableError",
    "ValidationError",
    "WebhookPayloadError",
    "api_error_from",
    "coerce_retry_after",
]

#: Plausibility bound for any retry hint, seconds. Anything above it is a broken clock or a
#: broken proxy, not a wait: clamping here is what keeps a hint out of native overflow. The
#: delay actually slept is capped again, and much lower, by ``RetryOptions.max_retry_after_ms``.
MAX_RETRY_AFTER_SECONDS = 24 * 3600.0


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
        # Only when there is one: assigning None would suppress the implicit context of a
        # `raise ... from err` and hide the original traceback.
        if cause is not None:
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


class PermissionDeniedError(ApiError):
    """403 - the key is valid but not allowed to do this (feature disabled, IP not allowed)."""


#: Deprecated spelling kept for 1.2 callers; it shadows the builtin, so it is not exported.
PermissionError = PermissionDeniedError


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

    def __init__(
        self, message: str, http_status: int, raw: Any = None, code: str = "sdk.bad_envelope"
    ) -> None:
        super().__init__(code, message, http_status=http_status, retryable=False, raw=raw)


class ResponseTooLargeError(ContractError):
    """The response body passed the size cap the SDK reads under (``sdk.response_too_large``).

    Not OOM and not a retryable transport failure: something answered with more than an answer.
    """

    def __init__(self, message: str, http_status: int) -> None:
        super().__init__(message, http_status, None, code="sdk.response_too_large")


class WebhookPayloadError(ContractError):
    """A delivery whose signature verified but whose body is not a usable event.

    Deliberately NOT a :class:`SignatureError`: the delivery is authentic, so a receiver that
    answers 401 to signature failures must not answer 401 to this one - the core would keep
    retrying a delivery that no retry can fix. Answer 400 and investigate the payload.
    """

    def __init__(self, message: str, raw: Any = None) -> None:
        super().__init__(message, 0, raw, code="webhook.bad_payload")


class SignatureError(OblodaiError):
    """Webhook verification failed (bad signature, stale timestamp, missing headers)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, http_status=0, retryable=False)


class AmountError(ConfigError, ValueError):
    """A string handed to the money helpers is not a decimal amount.

    Also a :class:`ValueError`, so ``except ValueError`` around the helpers keeps working.
    """

    def __init__(self, message: str) -> None:
        super().__init__("sdk.bad_amount", message, "amount")


#: Statuses a response without an envelope may carry transiently (LB/proxy/timeouts).
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def _text(value: Any) -> Optional[str]:
    """A field the envelope declares as a string, or ``None`` when it is anything else."""
    return value if isinstance(value, str) else None


def coerce_retry_after(value: Any) -> Optional[float]:
    """A retry hint in seconds: integer, float or numeric string, clamped and sane.

    Anything else - ``true``, ``null``, a list, ``"soon"``, ``NaN``, an infinity, a negative
    number - is no hint at all, and a hint bigger than :data:`MAX_RETRY_AFTER_SECONDS` is clamped
    rather than believed. The arithmetic stays in ``float``, so no width can overflow.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    if seconds != seconds or seconds in (float("inf"), float("-inf")):  # NaN / +-inf
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def api_error_from(
    http_status: int,
    detail: ErrorDetail,
    raw: Any = None,
    *,
    synthetic: bool = False,
    retry_after_header: Optional[float] = None,
) -> ApiError:
    """Build the right subclass from an error envelope (or a synthesized one) and the status.

    Every field is decoded on its own: an envelope where one field has the wrong JSON type still
    yields the rest, and never a ``TypeError`` from somewhere deeper in the SDK.
    """
    if not isinstance(detail, Mapping):
        detail = {}
    code = _text(detail.get("code")) or ""
    if not code:
        # No usable envelope: whatever answered did not speak the core's error shape.
        code, synthetic = "internal", True
    message = _text(detail.get("message")) or f"HTTP {http_status}"
    if synthetic and not _text(detail.get("message")):
        message = f"request failed with HTTP {http_status} (no envelope)"
    if synthetic:
        retryable = http_status in TRANSIENT_STATUSES
    else:
        declared = detail.get("retryable")
        # A literal boolean is the core speaking; anything else is noise, and the status decides.
        retryable = declared if isinstance(declared, bool) else http_status in (429, 503)
    body_retry_after = coerce_retry_after(detail.get("retry_after"))
    kwargs: Dict[str, Any] = {
        "http_status": http_status,
        "retryable": retryable,
        "retry_after": body_retry_after if body_retry_after is not None else retry_after_header,
        "request_id": _text(detail.get("request_id")),
        "field": _text(detail.get("field")),
        "synthetic": synthetic,
        "raw": raw,
    }
    if code == "idempotency.key_reused":
        return IdempotencyConflictError(code, message, **kwargs)
    by_status = {
        400: ValidationError,
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        429: RateLimitError,
        503: UnavailableError,
    }
    cls = by_status.get(http_status)
    if cls is None:
        cls = InternalError if http_status >= 500 else ApiError
    return cls(code, message, **kwargs)
