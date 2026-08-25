"""Webhook verification against real signed deliveries and against the rotation rules."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from oblodai import webhooks
from oblodai.core.errors import SignatureError
from oblodai.core.signing import sign_webhook
from tests.support.fixtures import load_webhook_samples, result_of

# The samples were delivered by the core's real dispatcher to the recorder, signed with the
# endpoint secret in force at that moment - the one returned by the rotate-secret call.
SAMPLES: List[Dict[str, Any]] = load_webhook_samples()
SECRET: str = result_of("POST /v1/webhooks/rotate-secret")["secret"]


@pytest.mark.parametrize(
    "index",
    range(len(SAMPLES)),
    ids=[s["headers"]["X-Webhook-Event"] + f"#{i}" for i, s in enumerate(SAMPLES)],
)
def test_verifies_every_recorded_delivery(index: int) -> None:
    sample = SAMPLES[index]
    raw = sample.get("raw") or json.dumps(sample["body"])
    ts = int(sample["headers"]["X-Webhook-Timestamp"])

    delivery = webhooks.verify_delivery(raw, sample["headers"], secret=SECRET, now=ts)
    assert delivery.event["uuid"] == sample["body"]["uuid"]
    assert delivery.id == sample["headers"]["X-Webhook-Id"]
    assert delivery.event_type == sample["headers"]["X-Webhook-Event"]
    assert delivery.event["type"] == sample["body"]["type"]
    assert isinstance(delivery.event["sequence"], int)
    assert sample["headers"]["X-Webhook-Event"].split(".")[0] in ("invoice", "payout", "wallet")

    with pytest.raises(SignatureError, match="does not match"):
        webhooks.verify(
            raw, sample["headers"], secret="some-other-secret", previous_secret="another", now=ts
        )


BODY = json.dumps(
    {
        "type": "payment",
        "uuid": "u1",
        "order_id": "o",
        "status": "paid",
        "is_final": True,
        "sequence": 7,
        "event_at": "2026-01-01T00:00:00Z",
    }
)
TS = 1_755_600_000


def headers(**overrides: str) -> Dict[str, str]:
    base = {
        "x-webhook-timestamp": str(TS),
        "x-webhook-signature": sign_webhook("whsec", TS, BODY),
    }
    base.update(overrides)
    return base


def test_accepts_a_valid_signature_with_case_insensitive_headers() -> None:
    event = webhooks.verify(BODY, headers(), secret="whsec", now=TS)
    assert event["type"] == "payment"
    # A list-valued header (ASGI/WSGI shapes) resolves to its first element.
    assert webhooks.verify(BODY, list(headers().items()), secret="whsec", now=TS)["uuid"] == "u1"


def test_rejects_a_wrong_secret_a_tampered_body_and_a_missing_header() -> None:
    with pytest.raises(SignatureError):
        webhooks.verify(BODY, headers(), secret="other", now=TS)
    with pytest.raises(SignatureError, match="does not match"):
        webhooks.verify(BODY.replace("paid", "paid_over"), headers(), secret="whsec", now=TS)
    with pytest.raises(SignatureError, match="missing"):
        webhooks.verify(BODY, {"x-webhook-signature": "aa"}, secret="whsec")


def test_rejects_stale_deliveries_unless_tolerance_is_disabled() -> None:
    with pytest.raises(SignatureError, match="outside"):
        webhooks.verify(BODY, headers(), secret="whsec", now=TS + 600)
    event = webhooks.verify(BODY, headers(), secret="whsec", now=TS + 600, tolerance_sec=0)
    assert event["uuid"] == "u1"


def test_verifies_during_a_rotation_via_the_prev_header_or_previous_secret() -> None:
    rotated = headers(
        **{
            "x-webhook-signature": sign_webhook("new", TS, BODY),
            "x-webhook-signature-prev": sign_webhook("old", TS, BODY),
        }
    )
    assert webhooks.verify(BODY, rotated, secret="old", now=TS)["uuid"] == "u1"  # not yet swapped
    assert webhooks.verify(BODY, rotated, secret="new", now=TS)["uuid"] == "u1"  # swapped
    assert (
        webhooks.verify(BODY, rotated, secret="unrelated", previous_secret="old", now=TS)["uuid"]
        == "u1"
    )


def test_parses_the_union_and_detects_stale_sequences() -> None:
    event = webhooks.parse(BODY)
    assert event["type"] == "payment"
    assert webhooks.is_stale(event, 7) is True
    assert webhooks.is_stale(event, 6) is False
    assert webhooks.is_stale(event, None) is False
    with pytest.raises(SignatureError, match="unknown event type"):
        webhooks.parse('{"type":"alien","uuid":"x"}')
    with pytest.raises(SignatureError, match="not JSON"):
        webhooks.parse("<html/>")
    with pytest.raises(SignatureError, match="type/uuid"):
        webhooks.parse('{"uuid":"x"}')


def test_accepts_the_header_objects_python_web_stacks_hand_over() -> None:
    from email.message import Message

    message = Message()
    for name, value in headers().items():
        message[name] = value
    # `http.server` and WSGI hand over an email.message.Message, not a dict.
    assert webhooks.verify(BODY, message, secret="whsec", now=TS)["uuid"] == "u1"
    # ASGI-style list values resolve to their first element.
    assert (
        webhooks.verify(BODY, {k: [v] for k, v in headers().items()}, secret="whsec", now=TS)[
            "uuid"
        ]
        == "u1"
    )


def test_a_non_integer_timestamp_header_is_a_signature_failure() -> None:
    with pytest.raises(SignatureError, match="not an integer"):
        webhooks.verify(BODY, headers(**{"x-webhook-timestamp": "later"}), secret="whsec")
