"""Подпись запросов и проверка вебхуков.

ВНИМАНИЕ: подпись ЗАПРОСА и подпись ВЕБХУКА — разные алгоритмы.

- Запрос: каноническая строка ``{timestamp}\\n{METHOD}\\n{path}\\n{body}``.
- Вебхук: ``{timestamp}.{сырое_тело}`` (точка-разделитель, без метода и пути), другой секрет.

Оба — HMAC-SHA256, результат hex в нижнем регистре.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import NamedTuple, Optional, Union


class SignedRequest(NamedTuple):
    timestamp: str
    signature: str
    body: str


def sign_request(
    secret: str,
    method: str,
    path: str,
    body: str,
    timestamp: Optional[str] = None,
) -> SignedRequest:
    """Считает подпись запроса.

    :param secret: секрет ключа мерчанта
    :param method: HTTP-метод в верхнем регистре (обычно ``POST``)
    :param path: путь запроса с ведущим слэшем, например ``/v1/payment``
    :param body: сериализованное тело (строка). Подписывается как есть.
    :param timestamp: фиксированный timestamp (для тестов); иначе текущее время
    """
    ts = timestamp if timestamp is not None else str(int(time.time()))
    signing_string = f"{ts}\n{method}\n{path}\n{body}"
    signature = hmac.new(
        secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return SignedRequest(timestamp=ts, signature=signature, body=body)


def compute_webhook_signature(secret: str, timestamp: str, raw_body: Union[str, bytes]) -> str:
    """Считает ожидаемую подпись вебхука для заданных timestamp и сырого тела."""
    raw = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    msg = f"{timestamp}.".encode("utf-8") + raw
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
