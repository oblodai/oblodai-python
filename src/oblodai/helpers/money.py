"""Amounts are decimal strings; never ``float()`` them (USDT has 6 decimals, BTC 8, ETH 18).

These helpers compare and add at arbitrary precision using integers, and keep the scale of the
widest operand so ``"10.000000" + "0.5"`` stays ``"10.500000"``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Tuple, Union

from ..core.errors import AmountError

__all__ = [
    "MAX_AMOUNT_LENGTH",
    "Amount",
    "add_amounts",
    "amount_equals",
    "compare_amounts",
    "is_zero_amount",
    "subtract_amounts",
]

#: Longest amount string these helpers will look at. The widest asset the core prices has 18
#: decimals; anything past this is not an amount, and refusing it up front is what keeps a
#: hostile string from turning into a multi-megabyte integer multiplication.
MAX_AMOUNT_LENGTH = 64

# ASCII digits only. `\d` also matches Arabic-Indic and Devanagari digits, which `int()` happily
# parses - so `"٥"` would become the amount 5 and no ledger anywhere would agree.
_DECIMAL = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")


#: What the helpers take: the wire's decimal string or a ``Decimal`` (never a ``float``).
Amount = Union[str, Decimal]


def _parts(amount: Amount) -> Tuple[bool, str, str]:
    if isinstance(amount, Decimal):
        if not amount.is_finite():
            raise AmountError(f"not a decimal amount: {amount}")
        amount = format(amount, "f")
    if not isinstance(amount, str):
        raise AmountError(f"not a decimal amount: {type(amount).__name__}")
    if len(amount) > MAX_AMOUNT_LENGTH:
        raise AmountError(
            f"amount string is {len(amount)} characters long (max {MAX_AMOUNT_LENGTH})"
        )
    if not _DECIMAL.match(amount):
        raise AmountError(f'not a decimal amount: "{amount}"')
    negative = amount.startswith("-")
    integer, _, fraction = (amount[1:] if negative else amount).partition(".")
    return negative, integer or "0", fraction


def _scaled(amount: Amount, scale: int) -> int:
    negative, integer, fraction = _parts(amount)
    value = int(integer + fraction.ljust(scale, "0"))
    return -value if negative else value


def _scale_of(*amounts: Amount) -> int:
    return max(len(_parts(a)[2]) for a in amounts)


def _unscale(value: int, scale: int) -> str:
    negative = value < 0
    digits = str(-value if negative else value).rjust(scale + 1, "0")
    integer = digits[: len(digits) - scale]
    fraction = digits[len(digits) - scale :]
    sign = "-" if negative else ""
    return f"{sign}{integer}.{fraction}" if scale else f"{sign}{integer}"


def compare_amounts(a: Amount, b: Amount) -> int:
    """``-1``, ``0`` or ``1``."""
    scale = _scale_of(a, b)
    left, right = _scaled(a, scale), _scaled(b, scale)
    return (left > right) - (left < right)


def amount_equals(a: Amount, b: Amount) -> bool:
    """``"25"`` and ``"25.000000"`` are the same amount."""
    return compare_amounts(a, b) == 0


def add_amounts(a: Amount, b: Amount) -> str:
    scale = _scale_of(a, b)
    return _unscale(_scaled(a, scale) + _scaled(b, scale), scale)


def subtract_amounts(a: Amount, b: Amount) -> str:
    scale = _scale_of(a, b)
    return _unscale(_scaled(a, scale) - _scaled(b, scale), scale)


def is_zero_amount(a: Amount) -> bool:
    return _scaled(a, _scale_of(a)) == 0
