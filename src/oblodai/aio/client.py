"""The asynchronous Oblodai client."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Mapping, Optional, Type

import httpx

from ..client import user_agent
from ..config import TimeoutLike, derive_settings, resolve_config
from ..core.atransport import AsyncTransport
from ..core.clock import SkewCorrectingClock
from ..core.engine import EngineSettings
from ..core.hooks import Hooks
from ..core.logger import Logger, NoopLogger
from ..core.retry import RetryOptions
from ..generated.aio_resources import (
    AsyncAccount,
    AsyncApiAllowlist,
    AsyncBatches,
    AsyncCheckout,
    AsyncDocuments,
    AsyncPaymentLinks,
    AsyncPayments,
    AsyncPayoutLinks,
    AsyncPayouts,
    AsyncReferrals,
    AsyncRefunds,
    AsyncSandbox,
    AsyncSettings,
    AsyncSplits,
    AsyncWallets,
    AsyncWebhooks,
)

__all__ = ["AsyncOblodai"]


class AsyncOblodai:
    """The async twin of :class:`~oblodai.Oblodai`; same namespaces, same options, awaited.

    >>> async with AsyncOblodai(public_id="oblodai_...", secret="oblodai_live_...") as oblodai:
    ...     invoice = await oblodai.payments.create({"amount": "25", "currency": "USDT"})
    ...     async for payment in oblodai.payments.history(limit=50):
    ...         ...
    """

    def __init__(
        self,
        *,
        public_id: Optional[str] = None,
        secret: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[TimeoutLike] = None,
        deadline: Optional[float] = None,
        retry: Optional[RetryOptions] = None,
        logger: Optional[Logger] = None,
        headers: Optional[Mapping[str, str]] = None,
        admin_token: Optional[str] = None,
        allow_insecure_base_url: Optional[bool] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        env: Optional[Mapping[str, str]] = None,
        hooks: Optional[Hooks] = None,
    ) -> None:
        config = resolve_config(
            public_id=public_id,
            secret=secret,
            base_url=base_url,
            timeout=timeout,
            deadline=deadline,
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
            headers=config.headers,
            admin_token=config.admin_token,
            retry=config.retry,
            timeout=config.timeout,
            deadline=config.deadline,
            clock=SkewCorrectingClock(),
            logger=config.logger or NoopLogger(),
            hooks=hooks,
        )
        self._attach(AsyncTransport(settings, http_client))

    def _attach(self, transport: AsyncTransport) -> None:
        #: The transport, exposed for advanced use (custom routes, tests).
        self.transport = transport

        self.payments = AsyncPayments(self.transport)
        self.payment_links = AsyncPaymentLinks(self.transport)
        self.refunds = AsyncRefunds(self.transport)
        self.payouts = AsyncPayouts(self.transport)
        self.payout_links = AsyncPayoutLinks(self.transport)
        self.batches = AsyncBatches(self.transport)
        self.splits = AsyncSplits(self.transport)
        self.wallets = AsyncWallets(self.transport)
        self.account = AsyncAccount(self.transport)
        self.webhooks = AsyncWebhooks(self.transport)
        self.settings = AsyncSettings(self.transport)
        self.api_allowlist = AsyncApiAllowlist(self.transport)
        self.referrals = AsyncReferrals(self.transport)
        self.documents = AsyncDocuments(self.transport)
        self.checkout = AsyncCheckout(self.transport)
        self.sandbox = AsyncSandbox(self.transport)

    def with_options(
        self,
        *,
        timeout: Optional[TimeoutLike] = None,
        max_retries: Optional[int] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> AsyncOblodai:
        """A new client with these overridden; the original is untouched, the HTTP pool shared.

        ``timeout`` is seconds per attempt, ``max_retries`` replaces ``RetryOptions.max_retries``,
        ``extra_headers`` are merged over the client's ``headers``. Closing the copy leaves the
        shared pool open; close the original when done.
        """
        settings = derive_settings(
            self.transport.settings,
            timeout=timeout,
            max_retries=max_retries,
            extra_headers=extra_headers,
        )
        clone = object.__new__(type(self))
        clone._attach(self.transport.derive(settings))
        return clone

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
