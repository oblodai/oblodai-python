"""The synchronous Oblodai client."""

from __future__ import annotations

import platform
from types import TracebackType
from typing import Any, Mapping, Optional, Type

import httpx

from ._version import SDK_VERSION
from .config import TimeoutLike, derive_settings, resolve_config
from .contract.version import CONTRACT_HASH
from .core.clock import SkewCorrectingClock
from .core.engine import EngineSettings
from .core.hooks import Hooks
from .core.logger import Logger, NoopLogger
from .core.retry import RetryOptions
from .core.transport import Transport
from .generated.resources import (
    Account,
    ApiAllowlist,
    Batches,
    Checkout,
    Documents,
    PaymentLinks,
    Payments,
    PayoutLinks,
    Payouts,
    Referrals,
    Refunds,
    Sandbox,
    Settings,
    Splits,
    Wallets,
    Webhooks,
)

__all__ = ["Oblodai", "user_agent"]


def user_agent(flavour: str = "python") -> str:
    """``oblodai-python/2.0.0 (contract abc123456789; python 3.12.3)``."""
    return (
        f"oblodai-{flavour}/{SDK_VERSION} "
        f"(contract {CONTRACT_HASH[:12]}; python {platform.python_version()})"
    )


class Oblodai:
    """The Oblodai API client. One instance per API key; safe to share across threads.

    >>> oblodai = Oblodai(public_id="oblodai_...", secret="oblodai_live_...")
    >>> invoice = oblodai.payments.create(
    ...     {"amount": "25", "currency": "USDT", "network": "tron", "order_id": "o-1"}
    ... )

    One key signs every route: credentials, base URL and admin token fall back to
    ``OBLODAI_PUBLIC_ID``, ``OBLODAI_SECRET``, ``OBLODAI_BASE_URL`` and ``OBLODAI_ADMIN_TOKEN``.
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
        http_client: Optional[httpx.Client] = None,
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
        self._attach(Transport(settings, http_client))

    def _attach(self, transport: Transport) -> None:
        #: The transport, exposed for advanced use (custom routes, tests).
        self.transport = transport

        self.payments = Payments(self.transport)
        self.payment_links = PaymentLinks(self.transport)
        self.refunds = Refunds(self.transport)
        self.payouts = Payouts(self.transport)
        self.payout_links = PayoutLinks(self.transport)
        self.batches = Batches(self.transport)
        self.splits = Splits(self.transport)
        self.wallets = Wallets(self.transport)
        self.account = Account(self.transport)
        self.webhooks = Webhooks(self.transport)
        self.settings = Settings(self.transport)
        self.api_allowlist = ApiAllowlist(self.transport)
        self.referrals = Referrals(self.transport)
        self.documents = Documents(self.transport)
        self.checkout = Checkout(self.transport)
        self.sandbox = Sandbox(self.transport)

    def with_options(
        self,
        *,
        timeout: Optional[TimeoutLike] = None,
        max_retries: Optional[int] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> Oblodai:
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

    def close(self) -> None:
        """Close the underlying HTTP connection pool (unless you supplied your own client)."""
        self.transport.close()

    def __enter__(self) -> Oblodai:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        creds = self.transport.settings.credentials
        who = creds.public_id if creds else "anonymous"
        return f"Oblodai(base_url={self.base_url!r}, public_id={who!r})"

    def __getattr__(self, name: str) -> Any:
        # A gentle nudge for people coming from the camelCase SDKs.
        alias = {"payoutLinks": "payout_links", "paymentLinks": "payment_links"}.get(name)
        if alias:
            raise AttributeError(f"{name!r} is spelled {alias!r} in the Python SDK")
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
