"""Amounts are decimal strings; never ``float()`` them (USDT has 6 decimals, BTC 8, ETH 18).

These helpers compare and add at arbitrary precision using integers, and keep the scale of the
widest operand so ``"10.000000" + "0.5"`` stays ``"10.500000"``.
"""

from __future__ import annotations

import re
from typing import Tuple

__all__ = [
    "add_amounts",
    "amount_equals",
    "compare_amounts",
    "is_zero_amount",
    "subtract_amounts",
]

_DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")


def _parts(amount: str) -> Tuple[bool, str, str]:
    if not isinstance(amount, str) or not _DECIMAL.match(amount):
        raise ValueError(f'not a decimal amount: "{amount}"')
    negative = amount.startswith("-")
    integer, _, fraction = (amount[1:] if negative else amount).partition(".")
    return negative, integer or "0", fraction


def _scaled(amount: str, scale: int) -> int:
    negative, integer, fraction = _parts(amount)
    value = int(integer + fraction.ljust(scale, "0"))
    return -value if negative else value


def _scale_of(*amounts: str) -> int:
    return max(len(_parts(a)[2]) for a in amounts)


def _unscale(value: int, scale: int) -> str:
    negative = value < 0
    digits = str(-value if negative else value).rjust(scale + 1, "0")
    integer = digits[: len(digits) - scale]
    fraction = digits[len(digits) - scale :]
    sign = "-" if negative else ""
    return f"{sign}{integer}.{fraction}" if scale else f"{sign}{integer}"


def compare_amounts(a: str, b: str) -> int:
    """``-1``, ``0`` or ``1``."""
    scale = _scale_of(a, b)
    left, right = _scaled(a, scale), _scaled(b, scale)
    return (left > right) - (left < right)


def amount_equals(a: str, b: str) -> bool:
    """``"25"`` and ``"25.000000"`` are the same amount."""
    return compare_amounts(a, b) == 0


def add_amounts(a: str, b: str) -> str:
    scale = _scale_of(a, b)
    return _unscale(_scaled(a, scale) + _scaled(b, scale), scale)


def subtract_amounts(a: str, b: str) -> str:
    scale = _scale_of(a, b)
    return _unscale(_scaled(a, scale) - _scaled(b, scale), scale)


def is_zero_amount(a: str) -> bool:
    return _scaled(a, _scale_of(a)) == 0
