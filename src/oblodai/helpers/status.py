"""Status vocabulary helpers - which invoice/payout states are terminal, paid or actionable."""

from __future__ import annotations

from typing import Tuple

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
FINAL_PAYMENT_STATUSES: Tuple[str, ...] = (
    "paid",
    "paid_over",
    "wrong_amount",
    "expired",
    "cancelled",
)

#: Payout statuses after which nothing else can happen.
FINAL_PAYOUT_STATUSES: Tuple[str, ...] = ("confirmed", "failed", "cancelled")


def is_payment_final(status: str) -> bool:
    return status in FINAL_PAYMENT_STATUSES


def is_payment_paid(status: str) -> bool:
    """``paid`` or ``paid_over`` - the merchant has the money.

    ``wrong_amount`` is NOT paid: resolve it with ``refunds.resolve``.
    """
    return status in ("paid", "paid_over")


def is_payment_underpaid(status: str) -> bool:
    """The invoice is waiting for a merchant decision (underpaid)."""
    return status == "wrong_amount"


def is_payout_final(status: str) -> bool:
    return status in FINAL_PAYOUT_STATUSES


def is_payout_succeeded(status: str) -> bool:
    """The payout reached the chain and is irreversible."""
    return status == "confirmed"
