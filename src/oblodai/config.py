"""Client options: explicit arguments merged with the environment, validated up front."""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Union
from urllib.parse import urlsplit

import httpx

from .core.engine import EngineSettings
from .core.errors import ConfigError
from .core.logger import Logger, console_logger
from .core.request import Credentials
from .core.retry import DEFAULT_RETRY, RetryOptions

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_DEADLINE",
    "DEFAULT_TIMEOUT",
    "ResolvedConfig",
    "TimeoutLike",
    "derive_settings",
    "resolve_config",
    "timeout_seconds",
]

DEFAULT_BASE_URL = "https://api.oblodai.com"
#: Per-attempt timeout, seconds.
DEFAULT_TIMEOUT = 30.0
#: Budget for the whole call including retries, seconds.
DEFAULT_DEADLINE = 90.0

#: Seconds, or an ``httpx.Timeout`` (its largest bound becomes the per-attempt timeout).
TimeoutLike = Union[float, httpx.Timeout]

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


@dataclass(frozen=True)
class ResolvedConfig:
    """What the client actually runs with."""

    base_url: str
    credentials: Optional[Credentials] = None
    #: Per-attempt timeout, seconds.
    timeout: float = DEFAULT_TIMEOUT
    #: Budget for the whole call including retries, seconds.
    deadline: float = DEFAULT_DEADLINE
    retry: RetryOptions = DEFAULT_RETRY
    logger: Optional[Logger] = None
    headers: Optional[Mapping[str, str]] = None
    admin_token: Optional[str] = None


def resolve_config(
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
    env: Optional[Mapping[str, str]] = None,
) -> ResolvedConfig:
    """Merge explicit options with the environment and validate what can be validated up front."""
    environ = os.environ if env is None else env

    resolved_base = (base_url or environ.get("OBLODAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    insecure = (
        allow_insecure_base_url
        if allow_insecure_base_url is not None
        else environ.get("OBLODAI_ALLOW_INSECURE") == "1"
    )
    _assert_base_url(resolved_base, insecure)

    pid = public_id or environ.get("OBLODAI_PUBLIC_ID")
    sec = secret or environ.get("OBLODAI_SECRET")
    if bool(pid) != bool(sec):
        raise ConfigError(
            "sdk.bad_config",
            "public_id and secret must be provided together (or set both OBLODAI_PUBLIC_ID and "
            "OBLODAI_SECRET)",
        )

    chosen_logger = logger
    if chosen_logger is None:
        level = (environ.get("OBLODAI_LOG") or "").lower()
        if level in ("debug", "info", "warn", "warning", "error"):
            chosen_logger = console_logger("warning" if level == "warn" else level)

    return ResolvedConfig(
        base_url=resolved_base,
        credentials=Credentials(pid, sec) if pid and sec else None,
        timeout=DEFAULT_TIMEOUT if timeout is None else timeout_seconds(timeout),
        deadline=DEFAULT_DEADLINE if deadline is None else _positive("deadline", deadline),
        retry=retry or DEFAULT_RETRY,
        logger=chosen_logger,
        headers=headers,
        admin_token=admin_token or environ.get("OBLODAI_ADMIN_TOKEN"),
    )


def derive_settings(
    settings: EngineSettings,
    *,
    timeout: Optional[TimeoutLike] = None,
    max_retries: Optional[int] = None,
    extra_headers: Optional[Mapping[str, str]] = None,
) -> EngineSettings:
    """``with_options``: a copy of the client's settings with these overridden (None keeps)."""
    changes: Dict[str, object] = {}
    if timeout is not None:
        changes["timeout"] = timeout_seconds(timeout)
    if max_retries is not None:
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ConfigError(
                "sdk.bad_config", "max_retries must be a non-negative integer", "max_retries"
            )
        changes["retry"] = dataclasses.replace(settings.retry, max_retries=max_retries)
    if extra_headers:
        changes["headers"] = {**(settings.headers or {}), **extra_headers}
    return dataclasses.replace(settings, **changes)  # type: ignore[arg-type]


def timeout_seconds(timeout: TimeoutLike) -> float:
    """The per-attempt timeout in seconds.

    The SDK bounds a whole attempt (connect, write and every byte of the response) with one
    number, so an ``httpx.Timeout`` contributes its largest bound; one with no bounds at all
    leaves the attempt to the call's ``deadline``.
    """
    if isinstance(timeout, httpx.Timeout):
        bounds = [
            b for b in (timeout.connect, timeout.read, timeout.write, timeout.pool) if b is not None
        ]
        return _positive("timeout", max(bounds)) if bounds else float("inf")
    return _positive("timeout", timeout)


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ConfigError("sdk.bad_config", f"{name} must be a positive number of seconds", name)
    return float(value)


def _assert_base_url(base_url: str, allow_insecure: bool) -> None:
    parts = urlsplit(base_url)
    if not parts.scheme or not parts.netloc:
        raise ConfigError("sdk.bad_config", f"base_url is not a valid URL: {base_url}", "base_url")
    if parts.scheme == "https":
        return
    host = (parts.hostname or "").lower()
    if parts.scheme == "http" and (allow_insecure or host in _LOCAL_HOSTS):
        return
    raise ConfigError(
        "sdk.bad_config",
        f"base_url must use https (got {parts.scheme}://{parts.netloc}); "
        "set allow_insecure_base_url=True for a local core",
        "base_url",
    )
