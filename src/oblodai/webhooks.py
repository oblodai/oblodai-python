"""Webhook verification - usable on its own, no client and no API key required::

    from oblodai import webhooks
    event = webhooks.verify(raw_body, request.headers, secret=endpoint_secret)

Deliveries are signed as::

    X-Webhook-Timestamp: <unix seconds>
    X-Webhook-Signature: hex(HMAC-SHA256(secret, "<ts>." + raw_body))
    X-Webhook-Signature-Prev: same, with the previous secret - only during a rotation overlap
    X-Webhook-Event: an event name of the contract (invoice.paid, conversion.completed, ...;
        all of them in WEBHOOK_EVENTS)
    X-Webhook-Id: stable per delivery (identical across retries of THAT delivery)
    X-Webhook-Event-Id: stable per STATE - the same for a resend of a state you already handled,
        and different as soon as the state differs. This is the idempotency key to keep.
    X-Webhook-Event-Time: unix seconds when the state change committed (order events by it)
    X-Webhook-Test: "true" on a rehearsal delivery (`webhooks.test`, sandbox) - the body carries
        `test: true` as well; never act on one as if money moved

Always verify over the RAW request bytes; a re-serialized parse will not match.

The MAC is checked BEFORE the freshness window, so an unauthenticated caller cannot use the
timestamp error as an oracle for what this endpoint considers "now". A delivery whose signature
verified but whose body is unusable raises :class:`~oblodai.WebhookPayloadError`
(``webhook.bad_payload``) rather than a :class:`~oblodai.SignatureError`: it is authentic, and a
receiver that answers 401 to signature failures must not answer 401 to it.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple, Union

if TYPE_CHECKING:  # `TypeGuard` is 3.10+; the runtime never needs it.
    from typing_extensions import TypeGuard

from .core.errors import ConfigError, SignatureError, WebhookPayloadError
from .core.signing import sign_webhook
from .core.util import HeaderSource, constant_time_equal, header_value
from .generated.events import (
    KNOWN_EVENT_KINDS,
    WEBHOOK_EVENTS,
    WEBHOOK_ID_FIELDS,
    WEBHOOK_MODELS,
    WebhookModel,
)

__all__ = [
    "HEADER_WEBHOOK_EVENT",
    "HEADER_WEBHOOK_EVENT_ID",
    "HEADER_WEBHOOK_EVENT_TIME",
    "HEADER_WEBHOOK_ID",
    "HEADER_WEBHOOK_SIGNATURE",
    "HEADER_WEBHOOK_SIGNATURE_PREV",
    "HEADER_WEBHOOK_TEST",
    "HEADER_WEBHOOK_TIMESTAMP",
    "KNOWN_EVENT_KINDS",
    "WEBHOOK_EVENTS",
    "WEBHOOK_ID_FIELDS",
    "WEBHOOK_MODELS",
    "SignatureError",
    "WebhookDeliveryInfo",
    "WebhookModel",
    "WebhookPayloadError",
    "is_known_event",
    "is_stale",
    "is_test_event",
    "object_id",
    "parse",
    "to_model",
    "verify",
    "verify_delivery",
]

HEADER_WEBHOOK_TIMESTAMP = "X-Webhook-Timestamp"
HEADER_WEBHOOK_SIGNATURE = "X-Webhook-Signature"
HEADER_WEBHOOK_SIGNATURE_PREV = "X-Webhook-Signature-Prev"
HEADER_WEBHOOK_EVENT = "X-Webhook-Event"
HEADER_WEBHOOK_ID = "X-Webhook-Id"
HEADER_WEBHOOK_EVENT_ID = "X-Webhook-Event-Id"
HEADER_WEBHOOK_EVENT_TIME = "X-Webhook-Event-Time"
HEADER_WEBHOOK_TEST = "X-Webhook-Test"

# KNOWN_EVENT_KINDS (the ``type`` discriminators of this snapshot of the contract),
# WEBHOOK_MODELS (kind -> model of the body), WEBHOOK_ID_FIELDS (kind -> the body field holding the
# object's id) and WEBHOOK_EVENTS (event name -> kind) are generated from the contract's ``webhooks``. A delivery naming a kind outside them is still returned - a
# newer core may add a kind, and dropping it would lose a real event.

RawBody = Union[str, bytes, bytearray]

#: A verified delivery body: a JSON object that always carries the string ``type`` (the kind); the
#: field holding the object's id is the kind's entry of :data:`WEBHOOK_ID_FIELDS` (read it with
#: :func:`object_id`). For attribute access parse it with the model of its kind - :func:`to_model`, or
#: ``WEBHOOK_MODELS[event["type"]].from_dict(event)`` (``payment`` -> ``PaymentWebhook``, ...).
AnyWebhookEvent = Dict[str, Any]
#: A delivery body whose ``type`` is one of :data:`KNOWN_EVENT_KINDS`.
WebhookEvent = Dict[str, Any]

# ASCII digits only: `int("١٢٣")` succeeds on Arabic-Indic digits, and a header the core never
# wrote must never be read as a number.
_ASCII_INT = re.compile(r"^[0-9]+$")
# Lowercase or uppercase hex, no `0x` prefix (which would silently fail the constant-time compare).
_HEX = re.compile(r"^[0-9a-fA-F]+$")


@dataclass(frozen=True)
class WebhookDeliveryInfo:
    """A verified delivery: the event plus the advisory headers worth keeping."""

    event: AnyWebhookEvent
    #: ``X-Webhook-Timestamp`` - unix seconds when this attempt was sent.
    sent_at: int
    #: ``X-Webhook-Id`` - stable across retries of the same DELIVERY. It is NOT enough to
    #: deduplicate on: a resend (``POST /v1/payment/resend``) is a new delivery of the state you
    #: may already have handled, and it carries a new id. Use :attr:`event_id`.
    id: Optional[str] = None
    #: ``X-Webhook-Event-Id`` - the id of the STATE this delivery carries: identical for the
    #: original, every retry of it and every resend of the same state, and different as soon as the
    #: state differs (an invoice that goes back to ``paid`` after a reorg, with another txid, is a
    #: new event and must be processed). Keep the ids you have handled and skip repeats of them.
    #: ``None`` from a core older than 2026-09-20; fall back to (uuid, status) idempotency then.
    event_id: Optional[str] = None
    #: ``X-Webhook-Event`` - the event name (``invoice.paid``, ``conversion.completed``, ...;
    #: :data:`WEBHOOK_EVENTS` maps each to its kind).
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
) -> AnyWebhookEvent:
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
    ``tolerance_sec=0`` disables the freshness window; a negative one is a mistake, not a wider
    window, and raises :class:`~oblodai.ConfigError`.
    """
    _assert_secrets(secret, previous_secret)
    if tolerance_sec < 0:
        raise ConfigError(
            "sdk.bad_config",
            f"tolerance_sec must be >= 0 (got {tolerance_sec}); use 0 to disable the freshness "
            "window",
            "tolerance_sec",
        )

    ts_raw = header_value(headers, HEADER_WEBHOOK_TIMESTAMP)
    signature = _hex_header(header_value(headers, HEADER_WEBHOOK_SIGNATURE))
    if not ts_raw or not signature:
        raise SignatureError(
            "webhook.missing_header",
            f"missing {HEADER_WEBHOOK_TIMESTAMP} or {HEADER_WEBHOOK_SIGNATURE}",
        )
    ts = _ascii_int(ts_raw)
    if ts is None:
        raise SignatureError("webhook.bad_signature", "timestamp header is not an integer")

    # MAC first: the freshness check below must never be reachable by an unauthenticated caller.
    prev_signature = _hex_header(header_value(headers, HEADER_WEBHOOK_SIGNATURE_PREV))
    # A merchant who has not swapped the stored secret yet verifies the Prev header with it; one
    # who already swapped but kept the old copy verifies the main header with the new secret.
    candidates: List[Tuple[str, str]] = [(signature, secret)]
    if prev_signature:
        candidates.append((prev_signature, secret))
    if previous_secret:
        candidates.append((signature, previous_secret))
        if prev_signature:
            candidates.append((prev_signature, previous_secret))
    body_bytes = _as_bytes(raw_body)
    ok = any(
        constant_time_equal(provided.lower(), sign_webhook(key, ts, body_bytes))
        for provided, key in candidates
    )
    if not ok:
        raise SignatureError("webhook.bad_signature", "signature does not match the body")

    if tolerance_sec > 0:
        current = int(time.time()) if now is None else now
        if abs(current - ts) > tolerance_sec:
            raise SignatureError(
                "webhook.stale_timestamp",
                f"delivery timestamp {ts} is outside the +/-{tolerance_sec}s window",
            )

    event = parse(body_bytes)
    return WebhookDeliveryInfo(
        event=event,
        sent_at=ts,
        id=header_value(headers, HEADER_WEBHOOK_ID),
        event_id=header_value(headers, HEADER_WEBHOOK_EVENT_ID),
        event_type=header_value(headers, HEADER_WEBHOOK_EVENT),
        event_time=_ascii_int(header_value(headers, HEADER_WEBHOOK_EVENT_TIME)),
        is_test=header_value(headers, HEADER_WEBHOOK_TEST) == "true" or is_test_event(event),
    )


def parse(raw_body: RawBody) -> AnyWebhookEvent:
    """Parse a (previously verified) delivery body into its event body; ``type`` tells the kind.

    An event kind this snapshot does not know is NOT an error: it is returned with its raw
    ``type`` string, so a receiver written against an older SDK still sees the delivery (and
    :func:`is_test_event` / :func:`is_stale` still work on it). Narrow the result with
    :func:`is_known_event`. A known kind must carry its object's id (:data:`WEBHOOK_ID_FIELDS`);
    of an unknown kind only ``type`` is required.
    """
    text = _as_bytes(raw_body).decode("utf-8", errors="replace")
    try:
        body: Any = json.loads(text)
    # A body nested thousands of levels deep exhausts the C stack instead of raising ValueError.
    except (ValueError, RecursionError):
        raise WebhookPayloadError("delivery body is not JSON") from None
    if not isinstance(body, Mapping):
        raise WebhookPayloadError("delivery body is not a JSON object")
    kind = body.get("type")
    if not isinstance(kind, str):
        raise WebhookPayloadError("delivery body lacks the string type field every event carries")
    id_field = WEBHOOK_ID_FIELDS.get(kind)
    if id_field is not None and not isinstance(body.get(id_field), str):
        raise WebhookPayloadError(f"{kind} delivery body lacks the string {id_field} field")
    return dict(body)


def object_id(event: Mapping[str, Any]) -> Optional[str]:
    """The id of the object the event is about - the field :data:`WEBHOOK_ID_FIELDS` names for its
    kind (a payment's ``uuid``, a conversion's ``id``, ...). Key per-object state on it, e.g. the
    last ``sequence`` for :func:`is_stale`.

    ``None`` for a kind this snapshot does not know (or one without such a field): acknowledge
    that delivery, but do not guess which field identifies its object.
    """
    if not isinstance(event, Mapping):
        return None
    kind = event.get("type")
    field = WEBHOOK_ID_FIELDS.get(kind) if isinstance(kind, str) else None
    value = event.get(field) if field is not None else None
    return value if isinstance(value, str) else None


def is_known_event(event: Mapping[str, Any]) -> TypeGuard[WebhookEvent]:
    """Is this one of the event kinds this snapshot of the contract declares?

    Use it to narrow what :func:`parse` returns before touching a kind-specific field::

        if webhooks.is_known_event(event) and event["type"] == "payment":
            ...

    ``False`` is not a reason to drop the delivery: acknowledge it, and act on what you do know.
    """
    return isinstance(event, Mapping) and event.get("type") in KNOWN_EVENT_KINDS


def to_model(event: Mapping[str, Any]) -> Optional[WebhookModel]:
    """The event parsed into the generated model of its kind; ``None`` for a kind this snapshot
    does not know (acknowledge it all the same)::

        model = webhooks.to_model(event)
        if isinstance(model, PaymentWebhook) and is_payment_paid(model.status):
            ...

    A known kind whose body does not fit its model raises
    :class:`~oblodai.WebhookPayloadError`: the delivery is authentic but unusable.
    """
    kind = event.get("type") if isinstance(event, Mapping) else None
    model = WEBHOOK_MODELS.get(kind) if isinstance(kind, str) else None
    if model is None:
        return None
    try:
        return model.from_dict(event)
    except (KeyError, TypeError, ValueError) as err:
        raise WebhookPayloadError(
            f"{event.get('type')} delivery does not fit {model.__name__}: {err}"
        ) from None


def is_test_event(event: Mapping[str, Any]) -> bool:
    """True for rehearsal deliveries (``webhooks.test``, sandbox).

    They are signed exactly like live ones, so a handler must check this and never act on a test
    event as if money moved.
    """
    if not isinstance(event, Mapping):
        return False
    return event.get("test") is True


def is_stale(event: Mapping[str, Any], last_processed_sequence: Optional[int]) -> bool:
    """Deliveries can arrive out of order (a retried ``paid`` after a ``refund``).

    Keep the last ``sequence`` you processed per object (:func:`object_id`) and skip anything not
    newer. An event with no usable ``sequence`` is never stale - dropping a delivery because a
    field was missing would lose money, so the safe answer is to process it - and this never
    raises.

    This is ORDERING, not deduplication, and the two used to be confused here. A resend carries a
    deliberately HIGHER sequence (a lower one could be discarded as a straggler, and a resend has
    to be able to correct a reorg reversal), so it is never stale and never a duplicate by
    ``X-Webhook-Id`` either. Deduplicate on :attr:`WebhookDeliveryInfo.event_id`; a handler that
    relied on these two alone shipped a resent ``invoice.paid`` twice.
    """
    if last_processed_sequence is None:
        return False
    if not isinstance(event, Mapping):
        return False
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return False
    return sequence <= last_processed_sequence


def _assert_secrets(secret: Any, previous_secret: Any) -> None:
    """No verification with an empty key: it would accept a MAC anyone can compute."""
    if not isinstance(secret, str) or not secret:
        raise ConfigError(
            "sdk.bad_config",
            "secret= must be the endpoint's non-empty signing secret; verifying with an empty "
            "key would accept forged deliveries",
            "secret",
        )
    if previous_secret is not None and (
        not isinstance(previous_secret, str) or not previous_secret
    ):
        raise ConfigError(
            "sdk.bad_config",
            "previous_secret= must be a non-empty secret when supplied; omit it entirely when "
            "no rotation is in flight",
            "previous_secret",
        )


def _hex_header(value: Optional[str]) -> Optional[str]:
    """A signature header: surrounding whitespace trimmed, hex in either case, no ``0x`` prefix."""
    if value is None:
        return None
    text = value.strip()
    return text if _HEX.match(text) else None


def _ascii_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = value.strip()
    return int(text) if _ASCII_INT.match(text) else None


def _as_bytes(raw: RawBody) -> bytes:
    return raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
