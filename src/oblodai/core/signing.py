"""Request signing - the exact recipe the core verifies (``crypto.SignRequest``), read from the
contract's ``x-oblodai-signing`` (:mod:`oblodai.generated.signing`)::

    canonical = REQUEST_CANONICAL_ORDER joined by REQUEST_CANONICAL_SEPARATOR
              = ts "\\n" METHOD "\\n" request_uri "\\n" idempotency_key "\\n" body   (today)
    signature = hex(HMAC-SHA256(secret, canonical))

- ``ts`` is unix seconds; the core accepts +/- :data:`SIGNATURE_SKEW_SECONDS` of skew.
- ``request_uri`` is path + raw query (``/v1/x?limit=1``), never the origin.
- The idempotency slot is the EMPTY string when no :data:`HEADER_IDEMPOTENCY_KEY` header is sent.
- ``body`` is the byte-exact request body; GETs sign an empty body.

The header names and the limits are the generated ones too: a header the core renames reaches
the SDK by regeneration alone. Pure: no clock, no I/O. The vectors in tests/unit/test_signing.py
come from the backend spec.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Dict, Optional, Tuple, Union

from ..generated.signing import (
    HEADER_IDEMPOTENCY_KEY,
    HEADER_PUBLIC_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    REQUEST_CANONICAL_ORDER,
    REQUEST_CANONICAL_SEPARATOR,
    SKEW_SECONDS,
    WEBHOOK_CANONICAL_ORDER,
    WEBHOOK_CANONICAL_SEPARATOR,
)

__all__ = [
    "HEADER_ADMIN_TOKEN",
    "HEADER_IDEMPOTENCY_KEY",
    "HEADER_PUBLIC_ID",
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "SIGNATURE_SKEW_SECONDS",
    "canonical_string",
    "sign_request",
    "sign_webhook",
]

Body = Union[str, bytes]


def _as_bytes(body: Body) -> bytes:
    return body.encode("utf-8") if isinstance(body, str) else bytes(body)


def _request_parts(
    ts: int, method: str, request_uri: str, body: bytes, idempotency_key: Optional[str]
) -> Dict[str, bytes]:
    return {
        "ts": str(ts).encode("utf-8"),
        "METHOD": method.upper().encode("utf-8"),
        "request_uri": request_uri.encode("utf-8"),
        "idempotency_key": (idempotency_key or "").encode("utf-8"),
        "body": body,
    }


def _canonical(order: Tuple[str, ...], separator: str, parts: Dict[str, bytes]) -> bytes:
    # Order and separator are read at call time from this module, which takes them from the
    # generated protocol; a part the contract names but this runtime does not fill is a KeyError.
    return separator.encode("utf-8").join(parts[p] for p in order)


def canonical_string(
    ts: int,
    method: str,
    request_uri: str,
    body: Body,
    idempotency_key: Optional[str] = None,
) -> str:
    """The exact string the MAC is computed over (useful when debugging a 401)."""
    parts = _request_parts(ts, method, request_uri, _as_bytes(body), idempotency_key)
    return _canonical(REQUEST_CANONICAL_ORDER, REQUEST_CANONICAL_SEPARATOR, parts).decode("utf-8")


def sign_request(
    secret: str,
    ts: int,
    method: str,
    request_uri: str,
    body: Body,
    idempotency_key: Optional[str] = None,
) -> str:
    """Lowercase hex HMAC-SHA256 of the canonical string, signed over the body BYTES."""
    parts = _request_parts(ts, method, request_uri, _as_bytes(body), idempotency_key)
    canonical = _canonical(REQUEST_CANONICAL_ORDER, REQUEST_CANONICAL_SEPARATOR, parts)
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def sign_webhook(secret: str, ts: int, payload: Body) -> str:
    """Webhook signature - ``webhook.Sign`` on the core side.

    ``signature = hex(HMAC-SHA256(secret, canonical))``, the canonical string being the parts of
    ``WEBHOOK_CANONICAL_ORDER`` (today ``"<unix ts>." + payload``). The payload is signed
    verbatim, so verifiers must use the raw request bytes, never a re-encoded parse of them.
    """
    parts = {"ts": str(ts).encode("utf-8"), "payload": _as_bytes(payload)}
    canonical = _canonical(WEBHOOK_CANONICAL_ORDER, WEBHOOK_CANONICAL_SEPARATOR, parts)
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


# HEADER_PUBLIC_ID, HEADER_SIGNATURE, HEADER_TIMESTAMP and HEADER_IDEMPOTENCY_KEY - the signed
# request headers as the core reads them - are the generated ones, re-exported above.

#: Gate on the unsigned onboarding routes of a self-hosted gateway. Not part of the signature and
#: not in ``x-oblodai-signing``.
HEADER_ADMIN_TOKEN = "X-Admin-Token"

#: Accepted clock skew on the core side, in seconds (``x-oblodai-signing.skew_seconds``).
SIGNATURE_SKEW_SECONDS = SKEW_SECONDS
