"""Per-call options: the five things a single call may override."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

__all__ = ["RequestOptions"]


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
