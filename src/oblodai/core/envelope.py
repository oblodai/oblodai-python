"""Response envelopes, as ``httpx``/``apiutil`` on the core write them::

    success : {"state": 0, "result": <payload>}
    list    : result = {"items": [...], "paginate": {total, per_page, offset, has_pages}}
    error   : {"error": {code, message, field?, retryable, retry_after?, request_id?}}

Every non-``bare`` route uses these; bare routes (PDF documents, health pages) bypass this module.
"""

from __future__ import annotations

import json
import math
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import ApiError, ContractError, ErrorDetail, api_error_from, coerce_retry_after

__all__ = [
    "as_page",
    "as_plain_list",
    "decode_envelope",
    "parse_retry_after",
    "unexpected_redirect",
]

_DELTA_SECONDS = re.compile(r"^[0-9]+$")


def decode_envelope(
    http_status: int,
    text: str,
    *,
    retry_after: Optional[str] = None,
    location: Optional[str] = None,
) -> Tuple[bool, Any]:
    """Interpret a response body.

    Returns ``(True, result)`` for a success envelope and ``(False, ApiError)`` for a failure.
    ``text`` is the raw body so non-JSON failures keep their evidence.
    """
    retry_after_header = parse_retry_after(retry_after)

    if 300 <= http_status < 400:
        return False, unexpected_redirect(http_status, location, text)

    body: Any = None
    if text:
        try:
            body = json.loads(text)
        # A body nested thousands of levels deep exhausts the C stack rather than raising
        # ValueError: it is still just an unparsable body, not a crash for the caller to catch.
        except (ValueError, RecursionError):
            if http_status >= 400:
                return False, api_error_from(
                    http_status,
                    {"code": "internal", "message": _no_envelope(http_status, text)},
                    text,
                    synthetic=True,
                    retry_after_header=retry_after_header,
                )
            raise ContractError(
                f"expected a JSON envelope, got {_describe(text)}", http_status, text
            ) from None

    if isinstance(body, Mapping) and isinstance(body.get("error"), Mapping):
        detail: ErrorDetail = dict(body["error"])  # type: ignore[assignment]
        return False, api_error_from(
            http_status, detail, body, retry_after_header=retry_after_header
        )
    if http_status >= 400:
        return False, api_error_from(
            http_status,
            {"code": "internal", "message": _no_envelope(http_status, text)},
            body,
            synthetic=True,
            retry_after_header=retry_after_header,
        )
    if isinstance(body, Mapping) and body.get("state") == 0 and "result" in body:
        return True, body["result"]
    raise ContractError(
        f"response is not a {{state:0,result}} envelope: {_describe(text)}", http_status, body
    )


def unexpected_redirect(http_status: int, location: Optional[str], raw: Any = None) -> ApiError:
    """The SDK never follows a redirect: a signature is only valid for the URI it was signed for.

    Raised both for a 3xx the SDK saw itself and for one an injected HTTP client followed behind
    its back (detected by the answer coming from a URL nobody asked for).
    """
    where = f" to {location}" if location else ""
    return api_error_from(
        http_status,
        {
            "code": "internal",
            "message": f"unexpected redirect (HTTP {http_status}){where}; check base_url",
        },
        raw,
        synthetic=True,
    )


def parse_retry_after(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """``Retry-After`` as delta-seconds or an HTTP-date.

    ``None`` when absent or unparsable; never negative, never unbounded - a header naming the
    year 9999 is clamped to :data:`~oblodai.core.errors.MAX_RETRY_AFTER_SECONDS` like any other
    implausible hint, and a date so far out that the timestamp arithmetic itself overflows is
    treated as no hint at all.
    """
    if not value:
        return None
    text = value.strip()
    if _DELTA_SECONDS.match(text):
        return coerce_retry_after(text)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    reference = time.time() if now is None else now
    try:
        delta = parsed.timestamp() - reference
    except (OverflowError, OSError, ValueError):
        return None
    return coerce_retry_after(math.ceil(delta))


def as_page(result: Any, http_status: int = 200) -> Dict[str, Any]:
    """Assert the paged-list shape on a decoded result; raises :class:`ContractError` otherwise."""
    if (
        isinstance(result, Mapping)
        and isinstance(result.get("items"), list)
        and isinstance(result.get("paginate"), Mapping)
    ):
        return dict(result)
    raise ContractError("expected {items, paginate} list result", http_status, result)


def as_plain_list(result: Any, http_status: int = 200) -> List[Any]:
    """Assert the ``{items}`` shape (lists the core caps by catalog size rather than paginating)."""
    if isinstance(result, Mapping) and isinstance(result.get("items"), list):
        return list(result["items"])
    raise ContractError("expected {items} list result", http_status, result)


def _no_envelope(status: int, text: str) -> str:
    return (
        f"HTTP {status} without an Oblodai error envelope ({_describe(text)}) - "
        "the answer came from a proxy or load balancer, not the API"
    )


def _describe(text: str) -> str:
    head = re.sub(r"\s+", " ", text[:120])
    if len(text) > 120:
        return f"{head}..."
    return head or "<empty body>"
