"""Builds the outgoing request - URL, headers, body - as a pure function of its inputs.

The signing material (what is signed) and the wire bytes (what is sent) come from one place and
cannot disagree. Nothing here touches the network or the clock.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Union
from urllib.parse import quote, urlsplit, urlunsplit

from .errors import ConfigError
from .route import RouteSpec
from .signing import (
    HEADER_ADMIN_TOKEN,
    HEADER_IDEMPOTENCY_KEY,
    HEADER_PUBLIC_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    sign_request,
)

__all__ = [
    "HEADER_REQUEST_ID",
    "NON_MONEY_NUMBERS",
    "RESERVED_HEADERS",
    "BuiltRequest",
    "Credentials",
    "Query",
    "QueryValue",
    "build_request",
    "encode_query",
    "fill_path",
    "join_url",
    "serialize_body",
]

QueryValue = Union[str, int, float, bool, None]
Query = Mapping[str, QueryValue]

#: Headers the SDK owns; a caller-supplied header with one of these names is dropped, compared
#: case-insensitively. An overridden ``Accept`` or ``User-Agent`` is merely wrong; an overridden
#: signing header would produce a request the core cannot verify.
#: Ties one call's attempts to the core's logs; one value for every attempt of a call. Not
#: reserved: a caller's own ``X-Request-ID`` header is the call's id when ``request_id`` is unset.
HEADER_REQUEST_ID = "X-Request-ID"

RESERVED_HEADERS = frozenset(
    h.lower()
    for h in (
        HEADER_PUBLIC_ID,
        HEADER_SIGNATURE,
        HEADER_TIMESTAMP,
        HEADER_IDEMPOTENCY_KEY,
        HEADER_ADMIN_TOKEN,
        "Accept",
        "Content-Type",
        "Content-Length",
        "Host",
        "User-Agent",
    )
)


@dataclass(frozen=True)
class Credentials:
    """One API key pair. The secret never reaches a repr, a log or a traceback."""

    public_id: str
    secret: str = field(repr=False)

    def __repr__(self) -> str:
        return f"Credentials(public_id={self.public_id!r}, secret='[redacted]')"


@dataclass(frozen=True)
class BuiltRequest:
    """Everything the HTTP layer needs, plus the string that was signed."""

    url: str
    method: str
    headers: Dict[str, str]
    content: Optional[bytes]
    #: What was signed (path + query); kept for debugging signature mismatches.
    request_uri: str


def build_request(
    *,
    base_url: str,
    route: RouteSpec,
    body: bytes,
    ts: int,
    user_agent: str,
    path_params: Optional[Mapping[str, Union[str, int]]] = None,
    query: Optional[Query] = None,
    credentials: Optional[Credentials] = None,
    idempotency_key: Optional[str] = None,
    extra_headers: Optional[Mapping[str, str]] = None,
    admin_token: Optional[str] = None,
    request_id: Optional[str] = None,
) -> BuiltRequest:
    """Assemble (and sign) one attempt of one call."""
    origin, prefix = join_url(base_url)
    path = prefix + fill_path(route.path, path_params)
    query_string = encode_query(query)
    request_uri = f"{path}?{query_string}" if query_string else path

    headers: Dict[str, str] = {}
    for name, value in (extra_headers or {}).items():
        if name.lower() in RESERVED_HEADERS:
            continue  # the SDK owns this one; a caller copy would be ignored or break signing
        if request_id and name.lower() == HEADER_REQUEST_ID.lower():
            continue  # replaced by the call's own id below, never sent twice  # the SDK owns this one; a caller copy would be ignored or break signing
        assert_header_value(name, value)
        headers[name] = value
    headers["Accept"] = "application/json"
    headers["User-Agent"] = user_agent
    has_body = route.method != "GET"
    if has_body:
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers[HEADER_IDEMPOTENCY_KEY] = idempotency_key
    if request_id:
        assert_header_value(HEADER_REQUEST_ID, request_id)
        headers[HEADER_REQUEST_ID] = request_id
    # Onboarding is the only surface the admin token gates; sending it anywhere else would leak a
    # gateway-wide credential onto every merchant request.
    if route.auth == "onboard" and admin_token:
        headers[HEADER_ADMIN_TOKEN] = admin_token

    if route.auth == "key":
        if credentials is None:
            raise ConfigError(
                "sdk.missing_credentials",
                f"{route.method} {route.path} needs the merchant's API key: pass "
                "public_id/secret to Oblodai() or set OBLODAI_PUBLIC_ID / OBLODAI_SECRET",
            )
        headers[HEADER_PUBLIC_ID] = credentials.public_id
        headers[HEADER_TIMESTAMP] = str(ts)
        headers[HEADER_SIGNATURE] = sign_request(
            credentials.secret,
            ts,
            route.method,
            request_uri,
            body if has_body else b"",
            idempotency_key,
        )

    return BuiltRequest(
        url=f"{origin}{request_uri}",
        method=route.method,
        headers=headers,
        content=body if has_body else None,
        request_uri=request_uri,
    )


def assert_header_value(name: str, value: str) -> None:
    """A caller header must be one header: no CR/LF, no bytes a header frame cannot carry.

    A value carrying ``\r\n`` splits into a second header (or a second request) on the wire.
    """
    if not isinstance(value, str):
        raise ConfigError(
            "sdk.bad_header", f'header "{name}" must be a string (got {type(value).__name__})', name
        )
    if "\r" in value or "\n" in value or "\0" in value:
        raise ConfigError(
            "sdk.bad_header",
            f'header "{name}" contains a line break; a header value must be a single line',
            name,
        )
    if not value.isascii():
        raise ConfigError(
            "sdk.bad_header",
            f'header "{name}" contains non-ASCII characters; encode them before sending',
            name,
        )


def join_url(base_url: str) -> tuple[str, str]:
    """Split a base URL into ``(origin, path_prefix)``; ``https://host/api`` keeps ``/api``."""
    scheme, netloc, path, _, _ = urlsplit(base_url)
    prefix = path.rstrip("/")
    origin = urlunsplit((scheme, netloc, "", "", ""))
    return origin, prefix


def fill_path(template: str, params: Optional[Mapping[str, Union[str, int]]] = None) -> str:
    """Substitute ``{name}`` segments; every placeholder must be supplied, values are encoded."""
    values = params or {}
    out = template
    while True:
        start = out.find("{")
        if start < 0:
            return out
        end = out.find("}", start)
        if end < 0:
            return out
        name = out[start + 1 : end]
        raw = values.get(name)
        text = "" if raw is None else str(raw)
        if text in ("", ".", "..") or "/" in text:
            raise ConfigError(
                "sdk.bad_path_param",
                f'path parameter "{name}" for {template} must be a non-empty single segment '
                f"(got {json.dumps(text)})",
                name,
            )
        out = out[:start] + quote(text, safe="") + out[end + 1 :]


def encode_query(query: Optional[Query]) -> str:
    """Percent-encode a query mapping, dropping ``None`` values and keeping insertion order."""
    if not query:
        return ""
    parts = []
    for key, value in query.items():
        if value is None:
            continue
        rendered = ("true" if value else "false") if isinstance(value, bool) else str(value)
        parts.append(f"{quote(str(key), safe='')}={quote(rendered, safe='')}")
    return "&".join(parts)


def _json_default(value: Any) -> str:
    """The one non-JSON type worth accepting: a ``Decimal``, rendered as the wire's own string.

    Anything else is a mistake the caller must see, named, before a request is signed.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ConfigError(
                "sdk.bad_body", f"request body carries a non-finite Decimal ({value})", "body"
            )
        return format(value, "f")
    raise ConfigError(
        "sdk.bad_body",
        f"request body carries a {type(value).__name__}, which is not JSON; amounts are decimal "
        "strings and times are RFC 3339 strings",
        "body",
    )


#: Request fields the contract types as a JSON ``number`` that are not money (a tolerance in
#: percent). A float anywhere else in a body is an amount losing precision; a unit test keeps this
#: set equal to the ``number`` properties of the contract's request schemas.
NON_MONEY_NUMBERS = frozenset({"accuracy_payment_percent"})


def reject_float_amounts(value: Any, path: str = "") -> None:
    """Walk a body; a ``float`` outside :data:`NON_MONEY_NUMBERS` is ``sdk.float_amount``."""
    if isinstance(value, float):
        raise ConfigError(
            "sdk.float_amount",
            f'amount passed as float ({value!r}); pass a string "{value!r}" or '
            f'Decimal("{value!r}") - float loses precision in money',
            path or "body",
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in NON_MONEY_NUMBERS and isinstance(item, (int, float)):
                continue
            reject_float_amounts(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_float_amounts(item, f"{path}[{index}]")


def serialize_body(body: Any, method: str) -> bytes:
    """Serialize a request body once; a missing POST body becomes ``{}``, GET signs nothing.

    ``allow_nan=False`` matters: Python renders ``float("nan")`` as the bare token ``NaN``, which
    is not JSON, and the core would answer 400 to a body the SDK swore it had encoded.
    """
    if method == "GET":
        return b""
    if body is None:
        return b"{}"
    reject_float_amounts(body)
    try:
        text = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
    except ValueError as err:  # allow_nan=False on a NaN/Infinity float
        raise ConfigError(
            "sdk.bad_body",
            f"request body is not JSON-serializable: {err}; amounts are decimal strings",
            "body",
        ) from err
    return text.encode("utf-8")
