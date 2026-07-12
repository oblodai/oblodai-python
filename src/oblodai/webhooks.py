"""Проверка входящих вебхуков.

Подпись вебхука отличается от подписи запроса (см. ``signing``). Секрет — из ``POST /v1/webhooks``,
а не ключ API.
"""

from __future__ import annotations

import hmac
import json
import time
from typing import Any, Mapping, Optional, Union

from ._transport import logger
from .errors import OblodaiSignatureError
from .signing import compute_webhook_signature


def verify_webhook(
    secret: str,
    raw_body: Union[str, bytes],
    headers: Mapping[str, str],
    max_age_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """Проверяет подпись и свежесть вебхука.

    Возвращает ``True`` при успехе, иначе бросает :class:`OblodaiSignatureError`.

    ВАЖНО: ``raw_body`` должен быть СЫРЫМ телом запроса (str или bytes) — тем же, что пришло по сети.
    Не передавайте пересериализованный JSON: подпись считается по байтам.

    Пробные тела (``"is_test": true``) НЕ подписаны — их этой функцией проверять не нужно.

    :param secret: секрет из ``POST /v1/webhooks``
    :param raw_body: сырое тело запроса
    :param headers: заголовки запроса (регистронезависимый доступ поддерживается)
    :param max_age_seconds: окно свежести для replay-защиты (0 — отключить). По умолчанию 300.
    :param now: текущее время в секундах (для тестов)
    """
    ts = _get_header(headers, "X-Webhook-Timestamp")
    sig = _get_header(headers, "X-Webhook-Signature")

    if not ts or not sig:
        logger.warning("oblodai: webhook verify failed: missing timestamp or signature")
        raise OblodaiSignatureError("Отсутствует timestamp или signature вебхука")

    expected = compute_webhook_signature(secret, ts, raw_body)
    if not hmac.compare_digest(expected, sig):
        logger.warning("oblodai: webhook verify failed: bad signature")
        raise OblodaiSignatureError("Подпись вебхука не совпадает")

    if max_age_seconds > 0:
        try:
            ts_val = int(ts)
        except ValueError:
            logger.warning("oblodai: webhook verify failed: invalid timestamp")
            raise OblodaiSignatureError("Некорректный timestamp вебхука")
        current = now if now is not None else time.time()
        age = abs(current - ts_val)
        if age > max_age_seconds:
            logger.warning(
                "oblodai: webhook verify failed: stale timestamp (age %ds > %ds)",
                int(age), max_age_seconds,
            )
            raise OblodaiSignatureError(
                f"Вебхук слишком старый: возраст {int(age)}с > {max_age_seconds}с"
            )

    logger.debug("oblodai: webhook signature ok")
    return True


def construct_event(
    secret: str,
    raw_body: Union[str, bytes],
    headers: Mapping[str, str],
    max_age_seconds: int = 300,
    now: Optional[float] = None,
) -> Any:
    """Проверяет вебхук и возвращает распарсенное тело (dict).

    Бросает :class:`OblodaiSignatureError` при неверной подписи.
    """
    verify_webhook(secret, raw_body, headers, max_age_seconds=max_age_seconds, now=now)
    text = raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
    return json.loads(text)


def _get_header(headers: Mapping[str, str], name: str) -> Optional[str]:
    # Точное совпадение
    if name in headers:
        return headers[name]
    # Регистронезависимый поиск
    lname = name.lower()
    for k, v in headers.items():
        if k.lower() == lname:
            return v
    return None
