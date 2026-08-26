"""Developer sandbox (``test_`` keys only): fake money, simulated deposits, webhook inspector."""

from __future__ import annotations

from typing import Any, Mapping, Optional, cast

from ..contract.models import (
    FaucetResult,
    SandboxDeposit,
    SandboxReplay,
    SandboxReset,
    WebhookDelivery,
)
from ..contract.requests import SandboxDepositBody, SandboxFaucetBody
from ..core.pagination import Page
from .base import Resource

__all__ = ["Sandbox"]


class Sandbox(Resource):
    """Everything a dev store can do that a live store cannot."""

    def faucet(self, params: SandboxFaucetBody, **options: Any) -> FaucetResult:
        """``POST /v1/sandbox/faucet`` - credit test funds."""
        return cast(FaucetResult, self._call("POST /v1/sandbox/faucet", params, **options))

    def deposit(self, params: SandboxDepositBody, **options: Any) -> SandboxDeposit:
        """``POST /v1/sandbox/deposit`` - simulate an on-chain deposit to an invoice.

        Repeat the same ``txid`` to add confirmations.
        """
        return cast(SandboxDeposit, self._call("POST /v1/sandbox/deposit", params, **options))

    def webhooks(
        self, params: Optional[Mapping[str, Any]] = None, **options: Any
    ) -> Page[WebhookDelivery]:
        """``GET /v1/sandbox/webhooks`` - deliveries with their payloads."""
        return self._page("GET /v1/sandbox/webhooks", params, **options)

    def replay(self, delivery_id: str, **options: Any) -> SandboxReplay:
        """``POST /v1/sandbox/webhooks/replay`` - re-send a terminal (delivered/dead) delivery."""
        return cast(
            SandboxReplay,
            self._call("POST /v1/sandbox/webhooks/replay", {"delivery_id": delivery_id}, **options),
        )

    def reset(self, **options: Any) -> SandboxReset:
        """``POST /v1/sandbox/reset`` - cancel open invoices and zero balances."""
        return cast(SandboxReset, self._call("POST /v1/sandbox/reset", **options))
