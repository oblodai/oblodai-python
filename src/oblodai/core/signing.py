"""Request signing - the exact recipe the core verifies (``crypto.SignRequest``)::

    canonical = ts "\\n" METHOD "\\n" request_uri "\\n" idempotency_key "\\n" body
    signature = hex(HMAC-SHA256(secret, canonical))

- ``ts`` is unix seconds; the core accepts +/-300 s of skew.
- ``request_uri`` is path + raw query (``/v1/x?limit=1``), never the origin.
- The idempotency slot is the EMPTY string when no ``Idempotency-Key`` header is sent.
- ``body`` is the byte-exact request body; GETs sign an empty body.

Pure: no clock, no I/O. The vectors in tests/unit/test_signing.py come from the core test suite.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional, Union

__all__ = [
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


def canonical_string(
    ts: int,
    method: str,
    request_uri: str,
    body: Body,
    idempotency_key: Optional[str] = None,
) -> str:
    """The exact string the MAC is computed over (useful when debugging a 401)."""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    return f"{ts}\n{method.upper()}\n{request_uri}\n{idempotency_key or ''}\n{text}"


def sign_request(
    secret: str,
    ts: int,
    method: str,
    request_uri: str,
    body: Body,
    idempotency_key: Optional[str] = None,
) -> str:
    """Lowercase hex HMAC-SHA256 of the canonical string, signed over the body BYTES."""
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    prefix = f"{ts}\n{method.upper()}\n{request_uri}\n{idempotency_key or ''}\n"
    mac.update(prefix.encode("utf-8"))
    mac.update(_as_bytes(body))
    return mac.hexdigest()


def sign_webhook(secret: str, ts: int, payload: Body) -> str:
    """Webhook signature - ``webhook.Sign`` on the core side.

    ``signature = hex(HMAC-SHA256(secret, "<unix ts>." + payload))``. The payload is signed
    verbatim, so verifiers must use the raw request bytes, never a re-encoded parse of them.
    """
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(f"{ts}.".encode())
    mac.update(_as_bytes(payload))
    return mac.hexdigest()


#: Signed request headers as the core reads them.
HEADER_PUBLIC_ID = "X-Public-Id"
HEADER_SIGNATURE = "X-Signature"
HEADER_TIMESTAMP = "X-Timestamp"
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"

#: Accepted clock skew on the core side, in seconds.
SIGNATURE_SKEW_SECONDS = 300
