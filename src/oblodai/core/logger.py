"""Minimal structured logger contract.

Anything with ``debug/info/warning/error(message, extra)`` fits (``logging.Logger``, structlog, a
test double). Field values that carry secrets are redacted before they reach the logger, so a debug
log never leaks a key, a signature, a cheque passcode or a claim URL.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Mapping, Optional, Protocol, TypeVar

__all__ = ["Logger", "NoopLogger", "StdlibLogger", "console_logger", "redact"]

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
_SENSITIVE = re.compile(
    r"secret|signature|passcode|token|authorization|password|claim_url", re.IGNORECASE
)

T = TypeVar("T")


def redact(value: T) -> T:
    """Replace values of sensitive-looking keys, recursively, without touching the original."""
    if isinstance(value, list):
        return [redact(item) for item in value]  # type: ignore[return-value]
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            out[key] = "[redacted]" if _SENSITIVE.search(str(key)) else redact(item)
        return out  # type: ignore[return-value]
    return value
