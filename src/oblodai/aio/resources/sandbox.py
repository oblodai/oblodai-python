"""Developer sandbox (``test_`` keys only): fake money, simulated deposits, webhook inspector."""

# GENERATED FILE - do not edit. Source: src/oblodai/resources/sandbox.py
# Regenerate with: python scripts/gen_async.py

from __future__ import annotations

from typing import Any, Mapping, Optional, cast

from ...contract.models import (
    FaucetResult,
    SandboxDeposit,
    SandboxReplay,
    SandboxReset,
    WebhookDelivery,
)
from ...contract.requests import SandboxDepositBody, SandboxFaucetBody
from ...core.pagination import AsyncPage
from ..base import AsyncResource

__all__ = ["AsyncSandbox"]


class AsyncSandbox(AsyncResource):
    """Everything a dev store can do that a live store cannot."""

    async def faucet(self, params: SandboxFaucetBody, **options: Any) -> FaucetResult:
        """``POST /v1/sandbox/faucet`` - credit test funds. Payout key."""
        return cast(FaucetResult, await self._call("POST /v1/sandbox/faucet", params, **options))

    async def deposit(self, params: SandboxDepositBody, **options: Any) -> SandboxDeposit:
        """``POST /v1/sandbox/deposit`` - simulate an on-chain deposit to an invoice.

        Repeat the same ``txid`` to add confirmations.
        """
        return cast(SandboxDeposit, await self._call("POST /v1/sandbox/deposit", params, **options))

    def webhooks(
        self, params: Optional[Mapping[str, Any]] = None, **options: Any
    ) -> AsyncPage[WebhookDelivery]:
        """``GET /v1/sandbox/webhooks`` - deliveries with their payloads."""
        return self._page("GET /v1/sandbox/webhooks", params, **options)

    async def replay(self, delivery_id: str, **options: Any) -> SandboxReplay:
        """``POST /v1/sandbox/webhooks/replay`` - re-send a terminal (delivered/dead) delivery."""
        return cast(
            SandboxReplay,
            await self._call(
                "POST /v1/sandbox/webhooks/replay", {"delivery_id": delivery_id}, **options
            ),
        )

    async def reset(self, **options: Any) -> SandboxReset:
        """``POST /v1/sandbox/reset`` - cancel open invoices and zero balances. Payout key."""
        return cast(SandboxReset, await self._call("POST /v1/sandbox/reset", **options))
