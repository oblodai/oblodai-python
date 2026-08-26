"""Client options: explicit arguments merged with the environment, validated up front."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import urlsplit

from .core.errors import ConfigError
from .core.logger import Logger, console_logger
from .core.request import Credentials
from .core.retry import DEFAULT_RETRY, RetryOptions

__all__ = ["DEFAULT_BASE_URL", "ResolvedConfig", "resolve_config"]

DEFAULT_BASE_URL = "https://api.oblodai.com"

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})


@dataclass(frozen=True)
class ResolvedConfig:
    """What the client actually runs with."""

    base_url: str
    credentials: Optional[Credentials] = None
    timeout_ms: float = 30_000.0
    deadline_ms: float = 90_000.0
    retry: RetryOptions = DEFAULT_RETRY
    logger: Optional[Logger] = None
    headers: Optional[Mapping[str, str]] = None
    admin_token: Optional[str] = None


def resolve_config(
    *,
    public_id: Optional[str] = None,
    secret: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_ms: Optional[float] = None,
    deadline_ms: Optional[float] = None,
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
        timeout_ms=30_000.0 if timeout_ms is None else timeout_ms,
        deadline_ms=90_000.0 if deadline_ms is None else deadline_ms,
        retry=retry or DEFAULT_RETRY,
        logger=chosen_logger,
        headers=headers,
        admin_token=admin_token or environ.get("OBLODAI_ADMIN_TOKEN"),
    )


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
