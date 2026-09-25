"""Idempotency keys.

On create-type routes the core caches the first response per key for the merchant and replays it
on retries; a different body under the same key is a 409 ``idempotency.key_reused``. The SDK
generates a key once per logical call and reuses it on every retry, so a timeout never turns into
a double payout.
"""

from __future__ import annotations

import re

from ..generated.signing import MAX_IDEMPOTENCY_KEY_LENGTH
from .errors import ConfigError
from .util import uuid4

__all__ = ["MAX_IDEMPOTENCY_KEY_LENGTH", "assert_idempotency_key", "new_idempotency_key"]

# MAX_IDEMPOTENCY_KEY_LENGTH is the contract's (``x-oblodai-signing``), re-exported above.

# Header values must be visible ASCII: the key is signed verbatim, so a stray control character or
# surrounding whitespace would silently change the MAC on one side only.
_PRINTABLE_ASCII = re.compile(r"^[\x21-\x7e]+$")


def new_idempotency_key() -> str:
    """A fresh key for one logical call (reused across that call's retries)."""
    return uuid4()


def assert_idempotency_key(key: str) -> None:
    """Validate a caller-supplied key before it is signed and sent."""
    if not isinstance(key, str) or not key:
        raise _invalid("idempotency_key must be a non-empty string")
    if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise _invalid(f"idempotency_key is too long (max {MAX_IDEMPOTENCY_KEY_LENGTH} chars)")
    if not _PRINTABLE_ASCII.match(key):
        raise _invalid("idempotency_key must be printable ASCII without spaces")


def _invalid(message: str) -> ConfigError:
    """A key the caller wrote: refused before anything is signed, so it is a ConfigError."""
    return ConfigError("sdk.bad_idempotency_key", message, "idempotency_key")
