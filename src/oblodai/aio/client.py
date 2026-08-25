"""The asynchronous Oblodai client."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Mapping, Optional, Type

import httpx

from ..client import user_agent
from ..config import resolve_config
from ..core.atransport import AsyncTransport
from ..core.clock import SkewCorrectingClock
from ..core.engine import EngineSettings
from ..core.logger import Logger, NoopLogger
from ..core.retry import RetryOptions
from .resources import (
    AsyncAccount,
    AsyncBatches,
    AsyncCatalog,
    AsyncDocuments,
    AsyncMerchants,
    AsyncPaymentLinks,
    AsyncPayments,
    AsyncPayoutLinks,
    AsyncPayouts,
    AsyncRefunds,
    AsyncSandbox,
    AsyncSettings,
    AsyncSplits,
    AsyncTransfers,
    AsyncWallets,
    AsyncWebhooks,
)

__all__ = ["AsyncOblodai"]


class AsyncOblodai:
    """The async twin of :class:`~oblodai.Oblodai`; same namespaces, same options, awaited.

    >>> async with AsyncOblodai(public_id="pk_live_...", secret="...") as oblodai:
    ...     invoice = await oblodai.payments.create({"amount": "25", "currency": "USDT"})
    ...     async for payment in oblodai.payments.history(limit=50):
    ...         ...
    """

    def __init__(
        self,
        *,
        public_id: Optional[str] = None,
        secret: Optional[str] = None,
        payout_public_id: Optional[str] = None,
        payout_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_ms: Optional[float] = None,
        deadline_ms: Optional[float] = None,
        retry: Optional[RetryOptions] = None,
        logger: Optional[Logger] = None,
        headers: Optional[Mapping[str, str]] = None,
        admin_token: Optional[str] = None,
        allow_insecure_base_url: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        config = resolve_config(
            public_id=public_id,
            secret=secret,
            payout_public_id=payout_public_id,
            payout_secret=payout_secret,
            base_url=base_url,
            timeout_ms=timeout_ms,
            deadline_ms=deadline_ms,
            retry=retry,
            logger=logger,
            headers=headers,
            admin_token=admin_token,
            allow_insecure_base_url=allow_insecure_base_url,
            env=env,
        )
        settings = EngineSettings(
            base_url=config.base_url,
            user_agent=user_agent(),
            credentials=config.credentials,
            payout_credentials=config.payout_credentials,
            headers=config.headers,
            admin_token=config.admin_token,
            retry=config.retry,
            timeout_ms=config.timeout_ms,
            deadline_ms=config.deadline_ms,
            clock=SkewCorrectingClock(),
            logger=config.logger or NoopLogger(),
        )
        #: The transport, exposed for advanced use (custom routes, tests).
        self.transport = AsyncTransport(settings, http_client)

        self.payments = AsyncPayments(self.transport)
        self.refunds = AsyncRefunds(self.transport)
        self.payouts = AsyncPayouts(self.transport)
        self.payout_links = AsyncPayoutLinks(self.transport)
        self.payment_links = AsyncPaymentLinks(self.transport)
        self.batches = AsyncBatches(self.transport)
        self.transfers = AsyncTransfers(self.transport)
        self.wallets = AsyncWallets(self.transport)
        self.webhooks = AsyncWebhooks(self.transport)
        self.documents = AsyncDocuments(self.transport)
        self.splits = AsyncSplits(self.transport)
        self.settings = AsyncSettings(self.transport)
        self.account = AsyncAccount(self.transport)
        self.catalog = AsyncCatalog(self.transport)
        self.sandbox = AsyncSandbox(self.transport)
        self.merchants = AsyncMerchants(self.transport)

    @property
    def base_url(self) -> str:
        return self.transport.settings.base_url

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool (unless you supplied your own client)."""
        await self.transport.aclose()

    async def __aenter__(self) -> AsyncOblodai:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        creds = self.transport.settings.credentials
        who = creds.public_id if creds else "anonymous"
        return f"AsyncOblodai(base_url={self.base_url!r}, public_id={who!r})"

    def __getattr__(self, name: str) -> Any:
        alias = {"payoutLinks": "payout_links", "paymentLinks": "payment_links"}.get(name)
        if alias:
            raise AttributeError(f"{name!r} is spelled {alias!r} in the Python SDK")
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
