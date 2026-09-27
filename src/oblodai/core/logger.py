"""Minimal structured logger contract.

Anything with ``debug/info/warning/error(message, extra)`` fits (``logging.Logger``, structlog, a
test double). Field values that carry secrets are redacted before they reach the logger, so a debug
log never leaks a key, a signature, a cheque passcode or a claim URL.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Mapping, Optional, Protocol, TypeVar
from urllib.parse import urlsplit

__all__ = [
    "Logger",
    "NoopLogger",
    "StdlibLogger",
    "console_logger",
    "is_sensitive",
    "is_sensitive_param",
    "redact",
    "redact_location",
]

LogFields = Mapping[str, Any]


class Logger(Protocol):
    """The four methods the transport calls."""

    def debug(self, message: str, fields: Optional[LogFields] = None) -> None: ...
    def info(self, message: str, fields: Optional[LogFields] = None) -> None: ...
    def warning(self, message: str, fields: Optional[LogFields] = None) -> None: ...
    def error(self, message: str, fields: Optional[LogFields] = None) -> None: ...


class NoopLogger:
    """Discards everything (the default)."""

    def debug(self, message: str, fields: Optional[LogFields] = None) -> None:
        return None

    def info(self, message: str, fields: Optional[LogFields] = None) -> None:
        return None

    def warning(self, message: str, fields: Optional[LogFields] = None) -> None:
        return None

    def error(self, message: str, fields: Optional[LogFields] = None) -> None:
        return None


class StdlibLogger:
    """Adapts a :class:`logging.Logger`; fields are redacted and passed as ``extra['oblodai']``."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger("oblodai")

    def _emit(self, level: int, message: str, fields: Optional[LogFields]) -> None:
        if fields:
            self._logger.log(level, "%s %s", message, redact(dict(fields)))
        else:
            self._logger.log(level, "%s", message)

    def debug(self, message: str, fields: Optional[LogFields] = None) -> None:
        self._emit(logging.DEBUG, message, fields)

    def info(self, message: str, fields: Optional[LogFields] = None) -> None:
        self._emit(logging.INFO, message, fields)

    def warning(self, message: str, fields: Optional[LogFields] = None) -> None:
        self._emit(logging.WARNING, message, fields)

    def error(self, message: str, fields: Optional[LogFields] = None) -> None:
        self._emit(logging.ERROR, message, fields)


def console_logger(level: str = "warning") -> StdlibLogger:
    """A stderr logger gated by level; ``OBLODAI_LOG=debug|info|warning|error`` selects it."""
    logger = logging.getLogger("oblodai")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[oblodai] %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))
    return StdlibLogger(logger)


#: Key names whose value is never logged. ``claim_url`` is spelled out because it does not read
#: like a secret and is one: the claim page URL embeds the cheque's one-time ``claim_token``.
#: ``device_code`` is the CLI device flow's polling secret; ``api-key`` covers ``X-Api-Key`` and
#: ``api_key`` (a proxy's key, or the key pair the onboarding answer carries).
_SENSITIVE = re.compile(
    r"secret|signature|passcode|token|authorization|password|claim_url|device_code|api[-_]?key",
    re.IGNORECASE,
)

T = TypeVar("T")


def is_sensitive(key: str) -> bool:
    """Whether a field or header of this name carries a secret (never logged, never ``repr``'d)."""
    return _SENSITIVE.search(key) is not None


#: Path and query parameters that carry a bearer secret: the claim token of
#: ``/v1/claim/{token}`` and ``/v1/aml/{token}``, and a signed link's ``sig`` / ``exp`` (plus any
#: name :func:`is_sensitive` already flags, and ``code``/``passcode`` style names).
_SENSITIVE_PARAM = re.compile(r"\A(sig|exp|code)\Z|_code\Z|passcode", re.IGNORECASE)


def is_sensitive_param(name: str) -> bool:
    """Whether a path or query parameter of this name carries a secret (masked in URLs the SDK
    shows: hook ``RequestInfo.url``, error messages)."""
    return is_sensitive(name) or _SENSITIVE_PARAM.search(name) is not None


def redact_location(url: Optional[str]) -> Optional[str]:
    """A URL a server pointed at (a redirect ``Location``), reduced to its scheme and host: its
    path and query may carry the very token or signature the request did."""
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.scheme or not parts.hostname:
        return "[redacted]"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}/[redacted]"


def redact(value: T) -> T:
    """Replace values of sensitive-looking keys, recursively, without touching the original."""
    if isinstance(value, list):
        return [redact(item) for item in value]  # type: ignore[return-value]
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[key] = "[redacted]" if is_sensitive(str(key)) else redact(item)
        return out  # type: ignore[return-value]
    return value
