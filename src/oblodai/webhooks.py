"""Webhook verification - usable on its own, no client and no API key required::

    from oblodai import webhooks
    event = webhooks.verify(raw_body, request.headers, secret=endpoint_secret)

Deliveries are signed as::

    X-Webhook-Timestamp: <unix seconds>
    X-Webhook-Signature: hex(HMAC-SHA256(secret, "<ts>." + raw_body))
    X-Webhook-Signature-Prev: same, with the previous secret - only during a rotation overlap
    X-Webhook-Event: invoice.<status> | payout.<status> | wallet.paid
    X-Webhook-Id: stable per delivery (identical across retries) - use it as your idempotency key
    X-Webhook-Event-Time: unix seconds when the state change committed (order events by it)
    X-Webhook-Test: "true" on a rehearsal delivery (`webhooks.test`, sandbox) - the body carries
        `test: true` as well; never act on one as if money moved

Always verify over the RAW request bytes; a re-serialized parse will not match.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple, Union

from .contract.models.webhooks import WebhookEvent
from .core.errors import SignatureError
from .core.signing import sign_webhook
from .core.util import HeaderSource, constant_time_equal, header_value

__all__ = [
    "HEADER_WEBHOOK_EVENT",
    "HEADER_WEBHOOK_EVENT_TIME",
    "HEADER_WEBHOOK_ID",
    "HEADER_WEBHOOK_SIGNATURE",
    "HEADER_WEBHOOK_SIGNATURE_PREV",
    "HEADER_WEBHOOK_TEST",
    "HEADER_WEBHOOK_TIMESTAMP",
    "SignatureError",
    "WebhookDeliveryInfo",
    "is_stale",
    "is_test_event",
    "parse",
    "verify",
    "verify_delivery",
]

HEADER_WEBHOOK_TIMESTAMP = "X-Webhook-Timestamp"
HEADER_WEBHOOK_SIGNATURE = "X-Webhook-Signature"
HEADER_WEBHOOK_SIGNATURE_PREV = "X-Webhook-Signature-Prev"
HEADER_WEBHOOK_EVENT = "X-Webhook-Event"
HEADER_WEBHOOK_ID = "X-Webhook-Id"
HEADER_WEBHOOK_EVENT_TIME = "X-Webhook-Event-Time"
HEADER_WEBHOOK_TEST = "X-Webhook-Test"

RawBody = Union[str, bytes, bytearray]


@dataclass(frozen=True)
class WebhookDeliveryInfo:
    """A verified delivery: the event plus the advisory headers worth keeping."""

    event: WebhookEvent
    #: ``X-Webhook-Timestamp`` - unix seconds when this attempt was sent.
    sent_at: int
    #: ``X-Webhook-Id`` - stable across retries of the same delivery; use it to deduplicate.
    id: Optional[str] = None
    #: ``X-Webhook-Event`` - ``invoice.<status>`` | ``payout.<status>`` | ``wallet.paid``.
    event_type: Optional[str] = None
    #: ``X-Webhook-Event-Time`` - unix seconds when the state change committed.
    event_time: Optional[int] = None
    #: A rehearsal delivery (``X-Webhook-Test: true`` / body ``test: true``): signed like a live
    #: one, but no money moved.
    is_test: bool = False


def verify(
    raw_body: RawBody,
    headers: HeaderSource,
    *,
    secret: str,
    previous_secret: Optional[str] = None,
    tolerance_sec: int = 300,
    now: Optional[int] = None,
) -> WebhookEvent:
    """Verify the signature and freshness, then parse.

    Raises :class:`~oblodai.SignatureError`; never returns an unverified body.
    """
    return verify_delivery(
        raw_body,
        headers,
        secret=secret,
        previous_secret=previous_secret,
        tolerance_sec=tolerance_sec,
        now=now,
    ).event


def verify_delivery(
    raw_body: RawBody,
    headers: HeaderSource,
    *,
    secret: str,
    previous_secret: Optional[str] = None,
    tolerance_sec: int = 300,
    now: Optional[int] = None,
) -> WebhookDeliveryInfo:
    """Like :func:`verify`, and also returns the delivery id, event type and times.

    ``previous_secret`` keeps deliveries queued before a rotation verifiable: they stay signed with
    the outgoing secret for their whole retry life (~26 h), so keep it that long after rotating.
    ``tolerance_sec=0`` disables the freshness window.
    """
    ts_raw = header_value(headers, HEADER_WEBHOOK_TIMESTAMP)
    signature = header_value(headers, HEADER_WEBHOOK_SIGNATURE)
    if not ts_raw or not signature:
        raise SignatureError(
            "webhook.missing_header",
            f"missing {HEADER_WEBHOOK_TIMESTAMP} or {HEADER_WEBHOOK_SIGNATURE}",
        )
    try:
        ts = int(ts_raw)
    except ValueError:
        raise SignatureError(
            "webhook.bad_signature", "timestamp header is not an integer"
        ) from None

    if tolerance_sec > 0:
        current = int(time.time()) if now is None else now
        if abs(current - ts) > tolerance_sec:
            raise SignatureError(
                "webhook.stale_timestamp",
                f"delivery timestamp {ts} is outside the +/-{tolerance_sec}s window",
            )

    prev_signature = header_value(headers, HEADER_WEBHOOK_SIGNATURE_PREV)
    # A merchant who has not swapped the stored secret yet verifies the Prev header with it; one
    # who already swapped but kept the old copy verifies the main header with the new secret.
    candidates: List[Tuple[str, str]] = [(signature, secret)]
    if prev_signature:
        candidates.append((prev_signature, secret))
    if previous_secret:
        candidates.append((signature, previous_secret))
        if prev_signature:
            candidates.append((prev_signature, previous_secret))
    ok = any(
        constant_time_equal(provided.lower(), sign_webhook(key, ts, _as_bytes(raw_body)))
        for provided, key in candidates
    )
    if not ok:
        raise SignatureError("webhook.bad_signature", "signature does not match the body")

    event_time_raw = header_value(headers, HEADER_WEBHOOK_EVENT_TIME)
    event_time = int(event_time_raw) if event_time_raw and event_time_raw.isdigit() else None
    event = parse(raw_body)
    return WebhookDeliveryInfo(
        event=event,
        sent_at=ts,
        id=header_value(headers, HEADER_WEBHOOK_ID),
        event_type=header_value(headers, HEADER_WEBHOOK_EVENT),
        event_time=event_time,
        is_test=header_value(headers, HEADER_WEBHOOK_TEST) == "true" or is_test_event(event),
    )


def parse(raw_body: RawBody) -> WebhookEvent:
    """Parse a (previously verified) delivery body into a typed event, discriminated by ``type``."""
    text = _as_bytes(raw_body).decode("utf-8", errors="replace")
    try:
        body: Any = json.loads(text)
    except ValueError:
        raise SignatureError("webhook.bad_signature", "body is not JSON") from None
    if (
        not isinstance(body, Mapping)
        or not isinstance(body.get("type"), str)
        or not isinstance(body.get("uuid"), str)
    ):
        raise SignatureError(
            "webhook.bad_signature", "body lacks the type/uuid fields every event carries"
        )
    if body["type"] not in ("payment", "payout", "wallet"):
        raise SignatureError("webhook.bad_signature", f'unknown event type "{body["type"]}"')
    return body  # type: ignore[return-value]


def is_test_event(event: Mapping[str, Any]) -> bool:
    """True for rehearsal deliveries (``webhooks.test``, sandbox).

    They are signed exactly like live ones, so a handler must check this and never act on a test
    event as if money moved.
    """
    return event.get("test") is True


def is_stale(event: Mapping[str, Any], last_processed_sequence: Optional[int]) -> bool:
    """Deliveries can arrive out of order (a retried ``paid`` after a ``refund``).

    Keep the last ``sequence`` you processed per object and skip anything not newer.
    """
    if last_processed_sequence is None:
        return False
    return int(event.get("sequence", 0)) <= last_processed_sequence


def _as_bytes(raw: RawBody) -> bytes:
    return raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
