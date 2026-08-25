"""Sandbox-only helpers: the faucet, simulated deposits, reset and webhook replay."""

from __future__ import annotations

from typing import Tuple, TypedDict

from .common import Money


class FaucetResult(TypedDict):
    """`/v1/sandbox/faucet` — test funds credited to the dev store's balance."""

    #: Asset that was credited.
    asset: str
    #: How much was credited.
    amount: Money
    #: Ledger entry the credit was booked as.
    journal_id: str


FAUCET_RESULT_KEYS: Tuple[str, ...] = ("asset", "amount", "journal_id")


class SandboxDeposit(TypedDict):
    """`/v1/sandbox/deposit` — a simulated on-chain payment of a sandbox invoice."""

    #: Invoice the deposit was attributed to.
    invoice_id: str
    #: Amount the synthetic transfer carried.
    amount: Money
    #: Confirmations the synthetic transfer was credited with.
    confirmations: int
    #: Synthetic transaction hash.
    txid: str


SANDBOX_DEPOSIT_KEYS: Tuple[str, ...] = ("invoice_id", "amount", "confirmations", "txid")


class SandboxReset(TypedDict):
    """`/v1/sandbox/reset` — what the wipe touched."""

    #: How many open invoices were cancelled.
    invoices_cancelled: int
    #: How many balances were set back to zero.
    balances_zeroed: int


SANDBOX_RESET_KEYS: Tuple[str, ...] = ("invoices_cancelled", "balances_zeroed")


class SandboxReplay(TypedDict):
    """`/v1/sandbox/webhooks/replay` — the delivery that was posted again."""

    ok: bool
    #: Id of the delivery that was replayed.
    delivery_id: str


SANDBOX_REPLAY_KEYS: Tuple[str, ...] = ("ok", "delivery_id")
