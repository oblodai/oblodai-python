"""The I/O-free half of a call.

:class:`CallEngine` is the whole lifecycle - serialize, sign, classify, decide to retry, correct
clock skew - expressed as a state machine that never touches a socket. The sync and the async
transport differ only in how they perform the :class:`Send` and :class:`Pause` steps the engine
asks for, so both clients share exactly the same rules.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Union

from ..contract.types import RouteSpec
from .clock import SkewCorrectingClock
from .envelope import decode_envelope
from .errors import ConfigError, ContractError, OblodaiError, TransportError
from .idempotency import assert_idempotency_key, new_idempotency_key
from .logger import Logger, NoopLogger, redact
from .request import Credentials, Query, build_request, serialize_body
from .retry import DEFAULT_RETRY, RetryOptions, retry_delay_ms, should_retry
from .signing import SIGNATURE_SKEW_SECONDS
from .steps import (
    MAX_FILE_BYTES,
    MAX_JSON_BYTES,
    BodyReader,
    Fail,
    Finish,
    Pause,
    RawResponse,
    Send,
    Step,
    assert_not_redirected,
)

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_JSON_BYTES",
    "BodyReader",
    "CallEngine",
    "CallOptions",
    "EngineSettings",
    "Fail",
    "Finish",
    "Pause",
    "RawResponse",
    "Send",
    "Step",
    "assert_not_redirected",
    "unwrap_result",
]

#: Error codes that mean the core rejected the signature because of the timestamp or the MAC.
SIGNATURE_FAILURE_CODES = frozenset({"merchant.bad_signature", "auth.bad_timestamp"})


@dataclass
class CallOptions:
    """Everything a single call may override."""

    body: Any = None
    query: Optional[Query] = None
    path_params: Optional[Mapping[str, Union[str, int]]] = None
    #: Supply your own key to make the call idempotent across process restarts.
    idempotency_key: Optional[str] = None
    #: Prefer the payout key pair on an ``any``-gated route.
    prefer_payout_key: bool = False
    timeout_ms: Optional[float] = None
    deadline_ms: Optional[float] = None
    #: Extra headers for this call alone, merged over the client's own. The SDK still owns the
    #: names in ``RESERVED_HEADERS``, and a value with CR/LF or non-ASCII bytes is a ConfigError.
    headers: Optional[Mapping[str, str]] = None


@dataclass
class EngineSettings:
    """Client-wide configuration the engine reads (never mutated per call).

    ``Transport.settings`` is public, so this object turns up in tracebacks, ``repr()`` and
    debugger panes: nothing secret is ever rendered.
    """

    base_url: str
    user_agent: str
    credentials: Optional[Credentials] = None
    payout_credentials: Optional[Credentials] = None
    headers: Optional[Mapping[str, str]] = field(default=None, repr=False)
    admin_token: Optional[str] = field(default=None, repr=False)
    retry: RetryOptions = DEFAULT_RETRY
    timeout_ms: float = 30_000.0
    deadline_ms: float = 90_000.0
    clock: SkewCorrectingClock = field(default_factory=SkewCorrectingClock)
    logger: Logger = field(default_factory=NoopLogger)

    def __repr__(self) -> str:
        return (
            f"EngineSettings(base_url={self.base_url!r}, user_agent={self.user_agent!r}, "
            f"credentials={self.credentials!r}, payout_credentials={self.payout_credentials!r}, "
            f"headers={'[redacted]' if self.headers else None}, "
            f"admin_token={'[redacted]' if self.admin_token else None}, "
            f"retry={self.retry!r}, timeout_ms={self.timeout_ms!r}, "
            f"deadline_ms={self.deadline_ms!r})"
        )


def _now_ms() -> float:
    return time.monotonic() * 1000.0


class CallEngine:
    """One logical call: attempts, retries, skew correction. Not reusable, not thread-safe."""

    def __init__(
        self,
        route: RouteSpec,
        options: CallOptions,
        settings: EngineSettings,
        now_ms: Optional[Callable[[], float]] = None,
    ) -> None:
        self._route = route
        self._options = options
        self._settings = settings
        self._now_ms = now_ms or _now_ms
        self._attempt = 0
        self._skew_tried = False
        self._skew_before = 0
        self._skew_installed = 0
        #: The offset the attempt in flight was signed with - not whatever the shared clock says
        #: now, which another thread may already have moved.
        self._signed_offset = 0
        self._body = b""
        self._idempotency_key: Optional[str] = None
        self._safe_to_repeat = False
        self._deadline_at = 0.0
        self._last_error: Optional[BaseException] = None
        self._label = f"{route.method} {route.path}"

    # -- lifecycle ---------------------------------------------------------------------------

    def begin(self) -> Step:
        route = self._route
        try:
            self._body = serialize_body(self._options.body, route.method)
            key = self._options.idempotency_key
            if key is not None:
                assert_idempotency_key(key)
                if not route.idempotent:
                    # The core ignores the header here, so a key would only make the SDK believe a
                    # re-send is deduplicated when it is not - the one belief that turns a lost
                    # response into a double spend.
                    raise ConfigError(
                        "sdk.idempotency_unsupported",
                        f"{self._label} does not deduplicate by Idempotency-Key; "
                        "remove idempotency_key from this call",
                        "idempotency_key",
                    )
            elif route.idempotent:
                key = new_idempotency_key()
            self._idempotency_key = key
        except OblodaiError as err:
            return Fail(err)

        self._safe_to_repeat = route.safe or (
            route.idempotent and self._idempotency_key is not None
        )
        budget = self._options.deadline_ms or self._settings.deadline_ms
        self._deadline_at = self._now_ms() + budget
        return self._send()

    def on_response(self, raw: RawResponse) -> Step:
        if 200 <= raw.status < 300:
            return Finish(raw)

        failure = self._classify(raw)
        self._settings.logger.debug(
            "response",
            redact(
                {
                    "route": self._label,
                    "status": raw.status,
                    "code": getattr(failure, "code", None),
                    "request_id": getattr(failure, "request_id", None),
                }
            ),
        )

        # Clock skew: the core rejected the timestamp/MAC. Learn its time from the `Date` header,
        # re-sign once, and keep the offset only if that attempt got past authentication.
        if raw.status == 401 and getattr(failure, "code", None) in SIGNATURE_FAILURE_CODES:
            clock = self._settings.clock
            if not self._skew_tried:
                offset = clock.observe_server_date(raw.header("date"))
                # Compared against what THIS attempt signed with: another thread may have moved
                # the shared offset in the meantime, and its correction is not evidence about
                # this request.
                if (
                    offset is not None
                    and abs(offset - self._signed_offset) > SIGNATURE_SKEW_SECONDS / 2
                ):
                    self._settings.logger.warning(
                        "clock skew detected; re-signing with server time",
                        {"route": self._label, "offset_sec": offset},
                    )
                    self._skew_tried = True
                    self._skew_before = self._signed_offset
                    self._skew_installed = offset
                    clock.correct(offset)
                    return self._send()
            else:
                # The corrected timestamp did not help: it was not skew. Put the old offset back
                # only if this call's correction is still the one in force.
                clock.revert_if_unchanged(self._skew_installed, self._skew_before)

        return self._after_failure(failure)

    def on_transport_error(self, error: BaseException) -> Step:
        return self._after_failure(error)

    def on_pause_done(self) -> Step:
        self._attempt += 1
        return self._send()

    # -- internals ---------------------------------------------------------------------------

    def _send(self) -> Step:
        route = self._route
        settings = self._settings
        extra: Optional[Mapping[str, str]] = settings.headers
        if self._options.headers:
            # Per-call headers win over the client's; both go through the same reserved-name and
            # value checks in `build_request`.
            merged: Dict[str, str] = dict(settings.headers or {})
            merged.update(self._options.headers)
            extra = merged
        ts, self._signed_offset = settings.clock.now_with_offset()
        try:
            request = build_request(
                base_url=settings.base_url,
                route=route,
                body=self._body,
                ts=ts,
                user_agent=settings.user_agent,
                path_params=self._options.path_params,
                query=self._options.query,
                credentials=self._credentials(),
                idempotency_key=self._idempotency_key,
                extra_headers=extra,
                admin_token=settings.admin_token,
            )
        except OblodaiError as err:
            return Fail(err)
        settings.logger.debug(
            "request",
            redact(
                {
                    "route": self._label,
                    "attempt": self._attempt,
                    "idempotency_key": self._idempotency_key,
                }
            ),
        )
        remaining = max(1.0, self._deadline_at - self._now_ms())
        timeout = min(self._options.timeout_ms or settings.timeout_ms, remaining)
        return Send(request, timeout, MAX_FILE_BYTES if route.bare else MAX_JSON_BYTES)

    def _credentials(self) -> Optional[Credentials]:
        """Which key pair signs a route. ``any`` routes take the payment key unless told otherwise."""
        route = self._route
        settings = self._settings
        if route.auth == "payout" or (route.auth == "any" and self._options.prefer_payout_key):
            return settings.payout_credentials or settings.credentials
        return settings.credentials

    def _classify(self, raw: RawResponse) -> BaseException:
        try:
            ok, decoded = decode_envelope(
                raw.status,
                raw.text,
                retry_after=raw.header("retry-after"),
                location=raw.header("location"),
            )
        except OblodaiError as err:
            return err
        if not ok:
            assert isinstance(decoded, BaseException)
            return decoded
        return ContractError(
            f"{self._label}: HTTP {raw.status} with a success envelope", raw.status, raw.text
        )

    def _after_failure(self, error: BaseException) -> Step:
        self._last_error = error
        if not should_retry(error, self._attempt, self._safe_to_repeat, self._settings.retry):
            return Fail(error)
        delay = retry_delay_ms(error, self._attempt, self._settings.retry)
        if self._now_ms() + delay > self._deadline_at:
            return Fail(
                TransportError(
                    "transport.deadline",
                    f"retry would exceed the call deadline; last error: {error}",
                    error,
                )
            )
        if delay <= 0:
            self._attempt += 1
            return self._send()
        return Pause(delay)


def unwrap_result(route: RouteSpec, raw: RawResponse) -> Any:
    """Decode a success envelope, surfacing the core's oversized-replay marker as an error."""
    ok, decoded = decode_envelope(raw.status, raw.text)
    if not ok:  # pragma: no cover - the engine already raised for error statuses
        assert isinstance(decoded, BaseException)
        raise decoded
    # The core replays a cached response by Idempotency-Key; when the original was too large to
    # cache it answers {ok, idempotent_replay: true, detail} instead of the object - surface that.
    if isinstance(decoded, Mapping) and decoded.get("idempotent_replay") is True:
        raise ContractError(
            f"{route.method} {route.path}: the request was already processed but its response was "
            f"too large to replay - fetch the result by order_id/reference "
            f"({decoded.get('detail', '')})",
            raw.status,
            decoded,
        )
    return decoded
