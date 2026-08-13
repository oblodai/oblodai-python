"""Клиенты Oblodai: синхронный (:class:`OblodaiClient`) и асинхронный (:class:`AsyncOblodaiClient`)."""

from __future__ import annotations

import logging
import os
import sys
import warnings
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


#: Префиксы тестовых (sandbox) учётных данных. Бизнес-эндпоинты с тестовым ключом работают
#: без изменений — между тестом и продом меняется только ключ.
TEST_PUBLIC_ID_PREFIX = "test_"
TEST_SECRET_PREFIX = "oblodai_test_"


def is_test_key(public_id: str) -> bool:
    """``True``, если ``public_id`` — тестовый (sandbox) ключ (префикс ``test_``).

    Тестовому public id соответствует секрет с префиксом ``oblodai_test_``. Только с таким
    ключом доступна группа ``client.sandbox``; живой ключ на sandbox-эндпоинтах получает
    HTTP 403 ``sandbox.live_key``.
    """
    return public_id.startswith(TEST_PUBLIC_ID_PREFIX)


#: Текст предупреждения при обращении к устаревшей группе ``client.refunds``.
_REFUNDS_DEPRECATED = (
    "oblodai: client.refunds устарела и будет удалена в 2.0. Используйте "
    "client.payments.refund_batch(...) — тот же эндпоинт POST /v1/refund/batch, "
    "та же семантика и та же идемпотентность. Группа refunds есть только в Python SDK; "
    "payments.refund_batch — канонический путь во всех SDK Oblodai."
)


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
            public_id,
            secret,
            base_url=base_url,
            timeout=timeout,
            retry=retry,
            http_client=http_client,
        )
        self.payments = _s.Payments(self._http)
        #: УСТАРЕЛО — доступ идёт через свойство ``refunds`` (см. ниже), которое предупреждает.
        self._refunds = _s.Refunds(self._http)
        self.payouts = _s.Payouts(self._http)
        self.batches = _s.Batches(self._http)
        self.payment_links = _s.PaymentLinks(self._http)
        #: Документированный СИНОНИМ ``payment_links`` (тот же объект). Канон во всех SDK
        #: Oblodai — ``payment_links``; ``links`` оставлен для совместимости и не будет удалён.
        self.links = self.payment_links
        self.payout_links = _s.PayoutLinks(self._http)
        self.splits = _s.Splits(self._http)
        self.wallets = _s.Wallets(self._http)
        self.account = _s.AccountResource(self._http)
        self.webhooks = _s.WebhooksResource(self._http)
        self.settings = _s.Settings(self._http)
        self.rates = _s.Rates(self._http)
        #: ТОЛЬКО для тестовых ключей (``test_…``) — см. :class:`oblodai.resources.sync_resources.Sandbox`.
        self.sandbox = _s.Sandbox(self._http)

    @property
    def refunds(self) -> "_s.Refunds":
        """УСТАРЕЛО. Канонический путь — :meth:`~oblodai.resources.sync_resources.Payments.refund_batch`.

        ``client.refunds.create_batch(...)`` и ``client.payments.refund_batch(...)`` бьют в один
        и тот же ``POST /v1/refund/batch`` с одним телом — это два имени одной операции. Группа
        ``refunds`` при этом существует только в Python SDK: в остальных четырёх (TS, Go, Rust,
        PHP) возвраты пачкой живут на платежах, поэтому код с ``client.refunds`` не переносится
        между языками. Ничего не удалено — вызов работает как раньше, но выдаёт
        :class:`DeprecationWarning`; удаление планируется в 2.0.
        """
        warnings.warn(_REFUNDS_DEPRECATED, DeprecationWarning, stacklevel=2)
        return self._refunds

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
            public_id,
            secret,
            base_url=base_url,
            timeout=timeout,
            retry=retry,
            http_client=http_client,
        )
        self.payments = _a.Payments(self._http)
        #: УСТАРЕЛО — доступ идёт через свойство ``refunds`` (см. ниже), которое предупреждает.
        self._refunds = _a.Refunds(self._http)
        self.payouts = _a.Payouts(self._http)
        self.batches = _a.Batches(self._http)
        self.payment_links = _a.PaymentLinks(self._http)
        #: Документированный СИНОНИМ ``payment_links`` (тот же объект). Канон во всех SDK
        #: Oblodai — ``payment_links``; ``links`` оставлен для совместимости и не будет удалён.
        self.links = self.payment_links
        self.payout_links = _a.PayoutLinks(self._http)
        self.splits = _a.Splits(self._http)
        self.wallets = _a.Wallets(self._http)
        self.account = _a.AccountResource(self._http)
        self.webhooks = _a.WebhooksResource(self._http)
        self.settings = _a.Settings(self._http)
        self.rates = _a.Rates(self._http)
        #: ТОЛЬКО для тестовых ключей (``test_…``) — см. :class:`oblodai.resources.async_resources.Sandbox`.
        self.sandbox = _a.Sandbox(self._http)

    @property
    def refunds(self) -> "_a.Refunds":
        """УСТАРЕЛО. Канонический путь — :meth:`~oblodai.resources.async_resources.Payments.refund_batch`.

        То же самое, что у синхронного клиента: ``client.refunds.create_batch(...)`` и
        ``client.payments.refund_batch(...)`` — одна операция (``POST /v1/refund/batch``) под
        двумя именами, и только второе имя есть в остальных SDK Oblodai. Вызов работает как
        раньше, но выдаёт :class:`DeprecationWarning`; удаление планируется в 2.0.
        """
        warnings.warn(_REFUNDS_DEPRECATED, DeprecationWarning, stacklevel=2)
        return self._refunds

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
