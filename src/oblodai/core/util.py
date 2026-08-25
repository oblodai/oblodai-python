"""Small pure helpers shared by the sync and async clients."""

from __future__ import annotations

import hmac
import uuid as _uuid
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, Sequence, Tuple, Union

__all__ = ["compact", "constant_time_equal", "header_value", "is_mapping", "uuid4"]


class SupportsItems(Protocol):
    """Anything header-shaped that can list its pairs (``email.message.Message``, ``httpx.Headers``)."""

    def items(self) -> Iterable[Tuple[Any, Any]]: ...


#: Every header shape a Python web stack hands out: a dict, a framework header object, an
#: ``email.message.Message`` (``http.server``), or a plain sequence of ``(name, value)`` pairs.
HeaderSource = Union[Mapping[str, Any], SupportsItems, Sequence[Any], None]


def uuid4() -> str:
    """RFC 4122 v4 UUID from the platform CSPRNG."""
    return str(_uuid.uuid4())


def constant_time_equal(a: str, b: str) -> bool:
    """Constant-time string equality (both sides are hex, so byte length equals char length)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def header_value(headers: HeaderSource, name: str) -> Optional[str]:
    """Case-insensitive header lookup over any header shape a web framework may hand us.

    Accepts anything with ``.items()`` (``dict``, ``httpx.Headers``, ``email.message.Message`` as
    ``http.server`` and WSGI hand it over) or a sequence of ``(name, value)`` pairs; a list value
    (ASGI style) yields its first element.
    """
    if headers is None:
        return None
    want = name.lower()
    pairs = getattr(headers, "items", None)
    items: Any = pairs() if callable(pairs) else headers
    for entry in items:
        try:
            key, value = entry
        except (TypeError, ValueError):
            continue
        key_text = key.decode("latin-1") if isinstance(key, bytes) else str(key)
        if key_text.lower() != want:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is None:
            return None
        return value.decode("latin-1") if isinstance(value, bytes) else str(value)
    return None


def compact(obj: Mapping[str, Any]) -> Dict[str, Any]:
    """Strip ``None`` values so they never reach the JSON encoder as explicit nulls."""
    return {k: v for k, v in obj.items() if v is not None}


def is_mapping(value: Any) -> bool:
    """True for a JSON object (and not for a list or a scalar)."""
    return isinstance(value, Mapping)
