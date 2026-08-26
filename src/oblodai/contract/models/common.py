"""Shared wire vocabulary: amounts, timestamps and the shapes every namespace reuses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union

from ..enums import FeeBearerResult

#: Decimal amount rendered by the core at the asset's own scale (``"10.000000"`` for USDT).
#: Never a float: parse it with :func:`decimal.Decimal` or the helpers in ``oblodai.helpers``.
#: Never ``<`` / ``>`` / ``sorted()`` either - it is a ``str``, so those compare lexicographically
#: and put ``"10"`` before ``"9"``. Use :func:`oblodai.compare_amounts`.
Money = str

#: RFC 3339 timestamp in UTC (``"2026-08-25T20:58:55Z"``).
Timestamp = str


class _BatchElementRequired(TypedDict):
    idx: int
    ok: bool


class BatchElement(_BatchElementRequired, total=False):
    """Element of a synchronous batch listing (``/v1/payout/mass``, ``/v1/payout/link/batch``)."""

    order_id: str
    result: Dict[str, Any]
    message: str
    error_code: str
    http_status: int


class FeeInfo(TypedDict):
    """How a fee was settled on a priced result. ``fee_type`` is the pricing mode."""

    commission: Money
    fee_bearer: FeeBearerResult
    fee_type: str


#: Kinds of asynchronous batches (the wire may carry a value newer than this snapshot).
BatchKind = str
#: Lifecycle of an asynchronous batch: ``queued``/``processing``/``done``/``stopped``.
BatchStatus = str


class OkResult(TypedDict):
    """A bare acknowledgement."""

    ok: bool


OK_RESULT_KEYS: Tuple[str, ...] = ("ok",)


class Paginate(TypedDict):
    """Offset pagination block of a ``{items, paginate}`` list result."""

    total: int
    per_page: int
    offset: int
    has_pages: bool


PAGINATE_KEYS: Tuple[str, ...] = ("total", "per_page", "offset", "has_pages")

__all__ = [
    "BATCH_ELEMENT_KEYS",
    "OK_RESULT_KEYS",
    "PAGINATE_KEYS",
    "BatchElement",
    "BatchKind",
    "BatchStatus",
    "FeeInfo",
    "Money",
    "OkResult",
    "Paginate",
    "Timestamp",
]

BATCH_ELEMENT_KEYS: Tuple[str, ...] = (
    "idx",
    "ok",
    "order_id",
    "result",
    "message",
    "error_code",
    "http_status",
)

# Re-exported for models that describe free-form nested payloads.
JsonValue = Union[None, bool, int, float, str, List[Any], Dict[str, Any]]
JsonObject = Dict[str, Any]
MaybeMoney = Optional[Money]
