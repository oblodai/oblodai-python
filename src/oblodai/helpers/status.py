"""Status vocabulary helpers - which invoice/payout states are terminal, paid or actionable.

The classes themselves are the contract's (``x-status-classes``, generated into
:mod:`oblodai.generated.statuses`); these are the 2.0 names for them.
"""

from __future__ import annotations

from typing import Tuple

from ..generated.enums import PaymentStatus
from ..generated.statuses import (
    PAYMENT_STATUS_FINAL,
    PAYOUT_STATUS_FINAL,
    is_payment_status_final,
    is_payment_status_success,
    is_payout_status_final,
    is_payout_status_success,
)

__all__ = [
    "FINAL_PAYMENT_STATUSES",
    "FINAL_PAYOUT_STATUSES",
    "is_payment_final",
    "is_payment_paid",
    "is_payment_underpaid",
    "is_payout_final",
    "is_payout_succeeded",
]

#: Invoice statuses after which nothing else can happen.
FINAL_PAYMENT_STATUSES: Tuple[str, ...] = PAYMENT_STATUS_FINAL

#: Payout statuses after which nothing else can happen.
FINAL_PAYOUT_STATUSES: Tuple[str, ...] = PAYOUT_STATUS_FINAL


def is_payment_final(status: str) -> bool:
    return is_payment_status_final(status)


def is_payment_paid(status: str) -> bool:
    """``paid`` or ``paid_over`` - the merchant has the money (the contract's success class).

    ``wrong_amount`` is NOT paid: resolve it with ``payments.resolve``.
    """
    return is_payment_status_success(status)


def is_payment_underpaid(status: str) -> bool:
    """The invoice is waiting for a merchant decision (underpaid)."""
    return status == PaymentStatus.WRONG_AMOUNT


def is_payout_final(status: str) -> bool:
    return is_payout_status_final(status)


def is_payout_succeeded(status: str) -> bool:
    """The payout reached the chain and is irreversible (the contract's success class)."""
    return is_payout_status_success(status)
