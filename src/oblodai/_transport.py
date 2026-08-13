"""Общее ядро транспорта (без I/O).

Здесь чистые функции, разделяемые синхронным и асинхронным клиентами: подготовка подписанного
запроса, разбор ответа в результат/ошибку и расчёт задержки backoff. Сам HTTP-вызов и сон делают
конкретные клиенты — так логика не дублируется между sync и async.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from .errors import OblodaiAPIError
from .signing import sign_request

DEFAULT_BASE_URL = "https://api.oblodai.com"
DEFAULT_TIMEOUT = 30.0

#: Логгер SDK. По умолчанию молчит (нет хендлера) — это и есть opt-in: логи включаются, только
#: если приложение настроит logging, либо через env-переменную ``OBLODAI_LOG`` (см. client.py).
#: ВАЖНО: никогда не логируем секрет, X-Signature, секрет вебхука и тела запросов/ответов.
logger = logging.getLogger("oblodai")


def _is_loopback_host(host: str) -> bool:
    """``True`` для петлевого хоста: ``localhost``, ``127.0.0.0/8``, ``::1``.

    Такой трафик не покидает машину, поэтому подслушать подпись на нём некому — это и есть
    исключение, ради которого локальные стенды (``http://localhost:8095``) продолжают работать.
    """
    h = host.strip().lower()
    if not h:
        return False
    # urlsplit отдаёт IPv6-хост в скобках: "[::1]".
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if h == "localhost" or h.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def validate_base_url(base_url: str) -> str:
    """Требует https:// для базового URL (исключение — петлевые хосты). Возвращает URL как есть.

    Зачем. Каждый подписанный запрос несёт заголовок ``X-Signature`` — HMAC тела и пути на
    секрете API-ключа. По ``http://`` он идёт открытым текстом: любой посредник на пути
    (прокси, Wi-Fi, оператор) читает подпись вместе с телом и может переиграть запрос,
    пока не истёк timestamp. Раньше SDK принимал ``http://`` молча, и опечатка в схеме или
    забытая настройка стенда тихо превращалась в утечку — теперь это ошибка на создании
    клиента, до первого запроса.

    Петлевой хост (``localhost``, ``127.0.0.1``, ``::1``) разрешён по ``http://``: трафик не
    уходит с машины, и на этом держатся локальные стенды.

    :raises ValueError: если схема не ``https`` и хост не петлевой, либо URL без схемы/хоста.
    """
    parts = urlsplit(base_url.strip())
    scheme = parts.scheme.lower()

    if not scheme or not parts.netloc:
        raise ValueError(
            "oblodai: base_url должен быть абсолютным URL со схемой и хостом, "
            f"например 'https://api.oblodai.com' (получено: {base_url!r})"
        )

    if scheme == "https":
        return base_url

    if scheme == "http" and _is_loopback_host(parts.hostname or ""):
        return base_url

    raise ValueError(
        f"oblodai: base_url должен использовать https:// (получено: {base_url!r}). "
        "По http:// заголовок подписи X-Signature уходит открытым текстом и его может "
        "перехватить любой посредник. Исключение — только локальные стенды на петлевом "
        "хосте: localhost, 127.0.0.1, ::1 (например 'http://localhost:8095')."
    )


@dataclass
class RetryConfig:
    max_attempts: int = 4
    initial_delay: float = 0.5
    max_delay: float = 30.0


@dataclass
class PreparedRequest:
    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[str]


def prepare_request(
    *,
    base_url: str,
    public_id: str,
    secret: str,
    path: str,
    payload: Any,
    signed: bool,
    method: str = "POST",
    idempotency_key: Optional[str] = None,
) -> PreparedRequest:
    """Готовит подписанный (или публичный) запрос: сериализует тело один раз и считает подпись по нему.

    ``idempotency_key`` уходит заголовком ``Idempotency-Key``. В подпись он НЕ входит
    (подпись покрывает только timestamp + метод + путь + тело), поэтому один и тот же ключ
    можно слать во всех попытках ретрая, хотя каждая попытка переподписывается заново.
    """
    url = base_url.rstrip("/") + path
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    body: Optional[str]

    if method == "GET":
        body = None
    else:
        # Компактный JSON — подписываем ровно эту строку и её же отправляем.
        body = json.dumps(payload if payload is not None else {}, separators=(",", ":"))

    if signed:
        # Для подписанного GET тело пустое: каноническая строка та же —
        # ``{ts}\nGET\n{path}\n`` (пустая строка после последнего \n).
        s = sign_request(secret, method, path, body if body is not None else "")
        headers["X-Public-Id"] = public_id
        headers["X-Timestamp"] = s.timestamp
        headers["X-Signature"] = s.signature

    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    return PreparedRequest(method=method, url=url, headers=headers, body=body)


def parse_retry_after(header: Optional[str]) -> Optional[float]:
    """Разбирает заголовок ``Retry-After`` в секунды.

    Поддерживает форму «секунды» (как отдаёт шлюз на 429: ``Retry-After: 60``). HTTP-date форму
    игнорируем (шлюз её не использует). ``None`` — если заголовка нет или он не число.
    """
    if not header:
        return None
    try:
        seconds = float(header.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def parse_response(status: int, text: str, retry_after: Optional[str] = None) -> Any:
    """Разбирает ответ. Возвращает ``result`` из конверта или бросает :class:`OblodaiAPIError`.

    Также обрабатывает случай ответа без конверта (единственное исключение — ``POST /v1/webhooks``,
    ``201 Created``). ``retry_after`` — значение заголовка ``Retry-After`` (для 429).
    """
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise OblodaiAPIError(
            "response.not_json", f"Ответ не является JSON (HTTP {status})", status, text
        )

    if isinstance(parsed, dict) and "error" in parsed:
        err = parsed.get("error") or {}
        raise OblodaiAPIError(
            err.get("code", "unknown"),
            err.get("message", "Неизвестная ошибка"),
            status,
            parsed,
            parse_retry_after(retry_after),
        )

    if not (200 <= status < 300):
        # 429 приходит телом `{state:1,message:"rate limit exceeded"}` без ключа `error` —
        # достаём message из тела и учитываем Retry-After.
        body_msg = parsed.get("message") if isinstance(parsed, dict) else None
        raise OblodaiAPIError(
            f"http.{status}",
            body_msg if isinstance(body_msg, str) else f"HTTP {status}",
            status,
            parsed,
            parse_retry_after(retry_after),
        )

    if isinstance(parsed, dict) and "result" in parsed:
        return parsed["result"]

    # Ответ без конверта (например, /v1/webhooks).
    return parsed


def should_retry(err: OblodaiAPIError, attempt: int, max_attempts: int) -> bool:
    return attempt < max_attempts and err.is_retriable


def backoff_delay(attempt: int, cfg: RetryConfig) -> float:
    """Экспоненциальная задержка с джиттером для попытки ``attempt`` (1-based)."""
    base = min(cfg.initial_delay * (2 ** (attempt - 1)), cfg.max_delay)
    jitter = random.uniform(0, cfg.initial_delay / 2)
    return base + jitter
