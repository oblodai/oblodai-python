"""Retry policy. Two questions decide every retry:

1. Can it succeed? - the core's ``retryable`` flag (authoritative when the core wrote the
   envelope), or a transient status for answers that carry no envelope.
2. Is repeating safe? - only for read-only routes and for writes the core deduplicates by
   idempotency key. A write the core does not deduplicate is never re-sent once it MAY have
   reached the core: a transport error or a proxy 503 after the request left the socket could
   mean the payout already happened.

An envelope error on an unsafe write is still retried when ``retryable`` - the core answered, so it
did not perform the operation (429/503/frozen/maturing all fail before any effect).
``Retry-After`` always wins over the computed backoff; otherwise exponential backoff with jitter.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Optional

from .errors import OblodaiError, TransportError

__all__ = ["DEFAULT_RETRY", "RetryOptions", "retry_delay_ms", "should_retry"]


@dataclass(frozen=True)
class RetryOptions:
    """Retry knobs. ``RetryOptions(max_retries=0)`` disables retries entirely."""

    #: Maximum number of retries after the first attempt.
    max_retries: int = 2
    #: Base delay for the first retry, ms.
    base_delay_ms: float = 250.0
    #: Upper bound for a computed (non-Retry-After) delay, ms.
    max_delay_ms: float = 4000.0
    #: Upper bound honoured for a server-provided Retry-After, ms.
    max_retry_after_ms: float = 30_000.0


DEFAULT_RETRY = RetryOptions()


def should_retry(
    error: BaseException, attempt: int, safe_to_repeat: bool, options: RetryOptions
) -> bool:
    """``attempt`` is 0 for the first retry decision (i.e. after attempt #1 failed)."""
    if attempt >= options.max_retries:
        return False
    if not isinstance(error, OblodaiError):
        return False
    if not error.retryable:
        return False
    if isinstance(error, TransportError):
        return safe_to_repeat
    # No core envelope: something in front of the core answered; the core may have done the work.
    if error.synthetic:
        return safe_to_repeat
    return True


def retry_delay_ms(
    error: BaseException,
    attempt: int,
    options: RetryOptions,
    rand: Optional[Callable[[], float]] = None,
) -> float:
    """Delay before the next attempt, in ms. ``rand`` is injectable for deterministic tests."""
    if isinstance(error, OblodaiError) and error.retry_after is not None and error.retry_after > 0:
        return min(error.retry_after * 1000.0, options.max_retry_after_ms)
    draw = rand or random.random
    exponential = min(options.max_delay_ms, options.base_delay_ms * float(2**attempt))
    # Full jitter with a floor so a burst of retries never lands in the same instant.
    return max(exponential // 4, float(int(draw() * exponential)))
