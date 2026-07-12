"""Ошибки Oblodai SDK.

Все ошибки API приходят в конверте ``{"error": {"code", "message"}}``, где ``code`` — машиночитаемый
идентификатор вида ``<домен>.<причина>`` (например ``payout.insufficient_funds``). Ветвитесь в коде по
``.code``, а не по тексту ``.message``.
"""

from __future__ import annotations

from typing import Any, Optional


class OblodaiError(Exception):
    """Базовая ошибка SDK. Все прочие ошибки наследуются от неё."""


class OblodaiAPIError(OblodaiError):
    """Ошибка, вернувшаяся от API (конверт ``error``).

    :ivar code: машиночитаемый код вида ``<домен>.<причина>``
    :ivar status: HTTP-статус ответа
    :ivar raw: сырое тело ответа (для отладки)
    """

    def __init__(
        self,
        code: str,
        message: str,
        status: int,
        raw: Any = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message
        self.status = status
        self.raw = raw
        # Рекомендованная сервером пауза перед повтором в секундах (из заголовка Retry-After),
        # если сервер её прислал — например, на 429 шлюз отдаёт `Retry-After: 60`.
        self.retry_after = retry_after

    @property
    def is_retriable(self) -> bool:
        """Временная ли ошибка (стоит ли повторять с backoff)."""
        if self.status >= 500:
            return True
        if self.status == 429:
            return True
        if self.code == "payout.funds_maturing":
            return True
        return False

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return f"OblodaiAPIError(code={self.code!r}, status={self.status}, message={self.message!r})"


class OblodaiConnectionError(OblodaiError):
    """Сетевая ошибка (соединение не удалось). Как правило, безопасно повторить с backoff."""

    def __init__(self, message: str, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.__cause__ = cause

    @property
    def is_retriable(self) -> bool:
        return True


class OblodaiTimeoutError(OblodaiConnectionError):
    """Таймаут запроса.

    Помните: таймаут НЕ значит, что операция не прошла. Благодаря идемпотентности по ``order_id``
    повтор безопасен — см. рецепт устойчивого клиента в документации.
    """


class OblodaiSignatureError(OblodaiError):
    """Ошибка проверки подписи вебхука (``verify_webhook``)."""
