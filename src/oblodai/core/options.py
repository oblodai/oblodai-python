"""Per-call options: the five things a single call may override."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = ["OPTION_NAMES", "RequestOptions", "options_from_kwargs"]


@dataclass(frozen=True)
class RequestOptions:
    """Overrides for one call. Every field left ``None`` falls back to the client's setting."""

    #: Your own key; generated automatically on routes the core deduplicates, and rejected on
    #: routes it does not.
    idempotency_key: Optional[str] = None
    #: Per-attempt timeout in seconds (capped by the client's ``deadline`` for the whole call).
    timeout: Optional[float] = None
    #: Retries after the first attempt for this call; overrides ``RetryOptions.max_retries``.
    max_retries: Optional[int] = None
    #: Extra headers for this call alone, merged over the client's own.
    extra_headers: Optional[Mapping[str, str]] = None
    #: Sent as ``X-Request-ID`` to tie your logs to ours; a ``uuid4`` is generated when omitted.
    request_id: Optional[str] = None


#: The keyword arguments that make up a :class:`RequestOptions`.
OPTION_NAMES = ("idempotency_key", "timeout", "max_retries", "extra_headers", "request_id")


def options_from_kwargs(options: Mapping[str, Any]) -> RequestOptions:
    """Build :class:`RequestOptions` from trailing keyword arguments; anything else is a TypeError."""
    unknown = sorted(set(options) - set(OPTION_NAMES))
    if unknown:
        raise TypeError(
            f"unexpected keyword argument(s) {', '.join(unknown)}; "
            f"resource methods accept {', '.join(OPTION_NAMES)}"
        )
    return RequestOptions(**options)
