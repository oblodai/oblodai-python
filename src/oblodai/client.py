"""Клиенты Oblodai: синхронный (:class:`OblodaiClient`) и асинхронный (:class:`AsyncOblodaiClient`)."""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import httpx

from ._http import AsyncHTTPClient, SyncHTTPClient
from ._transport import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, RetryConfig, logger
from .resources import async_resources as _a
from .resources import sync_resources as _s

#: Переменные окружения, из которых читаются учётные данные в ``from_env()``.
ENV_PUBLIC_ID = "OBLODAI_PUBLIC_ID"
ENV_SECRET = "OBLODAI_SECRET"
ENV_BASE_URL = "OBLODAI_BASE_URL"  # необязательная — переопределяет базовый URL API

#: Переменная окружения для zero-code включения логов SDK: debug/info/warning/error.
ENV_LOG = "OBLODAI_LOG"

_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

#: Маркер, чтобы не навесить наш StreamHandler дважды (idempotent bootstrap).
_ENV_HANDLER_ATTR = "_oblodai_env_handler"


def _bootstrap_env_logging() -> None:
    """Если задан ``OBLODAI_LOG``, один раз навешивает StreamHandler(stderr) на логгер "oblodai".

    Это opt-in для пользователя без единой строки кода. НЕ трогаем root-логгер и не вызываем
    ``logging.basicConfig`` — это дело приложения. Повторные вызовы безопасны (guard по маркеру).
    """
    raw = os.environ.get(ENV_LOG)
    if not raw:
        return
    level = _LOG_LEVELS.get(raw.strip().lower())
    if level is None:
        return
    # Guard от двойного добавления (например, при повторном импорте/создании клиента).
    if getattr(logger, _ENV_HANDLER_ATTR, False):
        logger.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    setattr(logger, _ENV_HANDLER_ATTR, True)


# Запускается на импорте модуля (client.py импортируется из oblodai/__init__.py).
_bootstrap_env_logging()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"oblodai: переменная окружения {name} не задана")
    return value


class OblodaiClient:
    """Синхронный клиент Oblodai API.

    Пример::

        from oblodai import OblodaiClient

        client = OblodaiClient(public_id="...", secret="...", base_url="https://api.oblodai.com")
        payment = client.payments.create(
            amount="10", currency="USD", order_id="order-1", to_currency="USDT", network="tron",
        )
        print(payment.address, payment.url)
    """

    def __init__(
        self,
        public_id: str,
        secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retry: Optional[RetryConfig] = RetryConfig(),
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._http = SyncHTTPClient(
            public_id, secret, base_url=base_url, timeout=timeout, retry=retry, http_client=http_client
        )
        self.payments = _s.Payments(self._http)
        self.refunds = _s.Refunds(self._http)
        self.payouts = _s.Payouts(self._http)
        self.batches = _s.Batches(self._http)
        self.payment_links = _s.PaymentLinks(self._http)
        #: Синоним ``payment_links`` (именование из пользовательской документации).
        self.links = self.payment_links
        self.payout_links = _s.PayoutLinks(self._http)
        self.splits = _s.Splits(self._http)
        self.wallets = _s.Wallets(self._http)
        self.account = _s.AccountResource(self._http)
        self.webhooks = _s.WebhooksResource(self._http)
        self.settings = _s.Settings(self._http)
        self.rates = _s.Rates(self._http)

    @classmethod
    def from_env(cls, *, base_url: Optional[str] = None, **kwargs: object) -> "OblodaiClient":
        """Создаёт клиента из переменных окружения.

        Читает ``OBLODAI_PUBLIC_ID`` и ``OBLODAI_SECRET`` (обязательны) и ``OBLODAI_BASE_URL``
        (необязательна). Явный ``base_url`` и прочие kwargs (``timeout``, ``retry``, ``http_client``)
        перекрывают окружение. Бросает :class:`ValueError`, если обязательная переменная не задана.
        """
        return cls(
            _require_env(ENV_PUBLIC_ID),
            _require_env(ENV_SECRET),
            base_url=base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL,
            **kwargs,  # type: ignore[arg-type]
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OblodaiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncOblodaiClient:
    """Асинхронный клиент Oblodai API.

    Пример::

        from oblodai import AsyncOblodaiClient

        async with AsyncOblodaiClient(public_id="...", secret="...") as client:
            payment = await client.payments.create(
                amount="10", currency="USD", order_id="order-1", to_currency="USDT", network="tron",
            )
    """

    def __init__(
        self,
        public_id: str,
        secret: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        retry: Optional[RetryConfig] = RetryConfig(),
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._http = AsyncHTTPClient(
            public_id, secret, base_url=base_url, timeout=timeout, retry=retry, http_client=http_client
        )
        self.payments = _a.Payments(self._http)
        self.refunds = _a.Refunds(self._http)
        self.payouts = _a.Payouts(self._http)
        self.batches = _a.Batches(self._http)
        self.payment_links = _a.PaymentLinks(self._http)
        #: Синоним ``payment_links`` (именование из пользовательской документации).
        self.links = self.payment_links
        self.payout_links = _a.PayoutLinks(self._http)
        self.splits = _a.Splits(self._http)
        self.wallets = _a.Wallets(self._http)
        self.account = _a.AccountResource(self._http)
        self.webhooks = _a.WebhooksResource(self._http)
        self.settings = _a.Settings(self._http)
        self.rates = _a.Rates(self._http)

    @classmethod
    def from_env(cls, *, base_url: Optional[str] = None, **kwargs: object) -> "AsyncOblodaiClient":
        """Создаёт асинхронного клиента из переменных окружения.

        Читает ``OBLODAI_PUBLIC_ID`` и ``OBLODAI_SECRET`` (обязательны) и ``OBLODAI_BASE_URL``
        (необязательна). Явные аргументы перекрывают окружение. Бросает :class:`ValueError`, если
        обязательная переменная не задана.
        """
        return cls(
            _require_env(ENV_PUBLIC_ID),
            _require_env(ENV_SECRET),
            base_url=base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL,
            **kwargs,  # type: ignore[arg-type]
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncOblodaiClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
