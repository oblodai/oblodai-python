"""Webhook verification against real signed deliveries and against the rotation rules."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from oblodai import webhooks
from oblodai.core.errors import ConfigError, SignatureError, WebhookPayloadError
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
    # Rehearsal deliveries (`webhooks.test`, sandbox) are signed like live ones and say so.
    assert delivery.is_test is (sample["body"].get("test") is True)
    assert delivery.is_test is (sample["headers"].get("X-Webhook-Test") == "true")
    assert webhooks.is_test_event(delivery.event) is delivery.is_test
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


def test_flags_a_rehearsal_delivery_from_the_header_alone() -> None:
    """The core sets `X-Webhook-Test` next to the body flag; either one marks the delivery."""
    plain = webhooks.verify_delivery(BODY, headers(), secret="whsec", now=TS)
    assert plain.is_test is False
    flagged = webhooks.verify_delivery(
        BODY, headers(**{"x-webhook-test": "true"}), secret="whsec", now=TS
    )
    assert flagged.is_test is True
    assert webhooks.is_test_event(flagged.event) is False  # the body itself said nothing


def test_parses_the_union_and_detects_stale_sequences() -> None:
    event = webhooks.parse(BODY)
    assert event["type"] == "payment"
    assert webhooks.is_stale(event, 7) is True
    assert webhooks.is_stale(event, 6) is False
    assert webhooks.is_stale(event, None) is False
    assert webhooks.is_test_event(event) is False
    assert webhooks.is_test_event({**event, "test": True}) is True
    # An event kind newer than this snapshot is returned, not refused: refusing would drop a real
    # delivery, and the raw `type` string is right there for the receiver to branch on.
    alien: Any = webhooks.parse('{"type":"alien","uuid":"x","sequence":3}')
    assert alien["type"] == "alien"
    assert webhooks.is_stale(alien, 3) is True
    assert webhooks.is_test_event(alien) is False
    # A body that verified but cannot be used is a CONTRACT failure, never a signature one:
    # a receiver answering 401 to SignatureError must not answer 401 to an authentic delivery.
    for body in ("<html/>", '{"uuid":"x"}', "[1,2]"):
        with pytest.raises(WebhookPayloadError) as excinfo:
            webhooks.parse(body)
        assert excinfo.value.code == "webhook.bad_payload"
        assert not isinstance(excinfo.value, SignatureError)


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


# --- the rules a forged or malformed delivery must run into ---------------------------------


def test_an_empty_secret_is_refused_before_any_crypto_runs() -> None:
    """Verifying with "" would accept a MAC anybody can compute - it must never be attempted."""
    for bad in ("", None):
        with pytest.raises(ConfigError) as excinfo:
            webhooks.verify(BODY, headers(), secret=bad, now=TS)  # type: ignore[arg-type]
        assert excinfo.value.field == "secret"
    # Same for an empty previous secret during a rotation.
    with pytest.raises(ConfigError) as excinfo:
        webhooks.verify(BODY, headers(), secret="whsec", previous_secret="", now=TS)
    assert excinfo.value.field == "previous_secret"


def test_a_negative_tolerance_is_a_config_error_not_a_wider_window() -> None:
    with pytest.raises(ConfigError) as excinfo:
        webhooks.verify(BODY, headers(), secret="whsec", tolerance_sec=-1, now=TS)
    assert excinfo.value.field == "tolerance_sec"


def test_the_mac_is_checked_before_the_freshness_window() -> None:
    """The timestamp error must not be reachable with a wrong signature.

    Otherwise an unauthenticated caller can probe what this endpoint believes the time is.
    """
    stale_and_forged = headers(**{"x-webhook-timestamp": str(TS - 100_000)})
    with pytest.raises(SignatureError) as excinfo:
        webhooks.verify(BODY, stale_and_forged, secret="whsec", now=TS)
    assert excinfo.value.code == "webhook.bad_signature"


def test_a_signature_header_may_be_padded_or_uppercase_but_not_0x_prefixed() -> None:
    good = sign_webhook("whsec", TS, BODY)
    assert webhooks.verify(
        BODY, headers(**{"x-webhook-signature": f"  {good} "}), secret="whsec", now=TS
    )
    assert webhooks.verify(
        BODY, headers(**{"x-webhook-signature": good.upper()}), secret="whsec", now=TS
    )
    with pytest.raises(SignatureError, match="missing"):
        webhooks.verify(
            BODY, headers(**{"x-webhook-signature": f"0x{good}"}), secret="whsec", now=TS
        )


def test_a_non_ascii_digit_timestamp_is_not_a_number() -> None:
    """`int("\u0661\u0662\u0663")` parses Arabic-Indic digits; the core never wrote those."""
    with pytest.raises(SignatureError, match="not an integer"):
        webhooks.verify(
            BODY, headers(**{"x-webhook-timestamp": "\u0661\u0662\u0663"}), secret="whsec"
        )


def test_is_stale_never_raises_and_never_skips_a_delivery_it_cannot_judge() -> None:
    """A missing or unusable `sequence` must be processed, not skipped: skipping loses money."""
    assert webhooks.is_stale({"type": "payment", "uuid": "u"}, 5) is False
    assert webhooks.is_stale({"sequence": None}, 5) is False
    assert webhooks.is_stale({"sequence": "7"}, 5) is False
    assert webhooks.is_stale({"sequence": float("nan")}, 5) is False
    assert webhooks.is_stale({"sequence": True}, 5) is False
    assert webhooks.is_stale({"sequence": 4}, 5) is True


def test_a_deeply_nested_body_is_a_payload_error_not_a_recursion_crash() -> None:
    """An attacker controls these bytes; `json.loads` blows the C stack long before it gives up."""
    bomb = "[" * 100_000 + "]" * 100_000
    with pytest.raises(WebhookPayloadError) as excinfo:
        webhooks.parse(bomb)
    assert excinfo.value.code == "webhook.bad_payload"


def test_a_verified_but_unusable_body_still_reports_the_delivery_as_authentic() -> None:
    broken = '{"type":"payment"}'
    signed = {
        "x-webhook-timestamp": str(TS),
        "x-webhook-signature": sign_webhook("whsec", TS, broken),
    }
    with pytest.raises(WebhookPayloadError):
        webhooks.verify(broken, signed, secret="whsec", now=TS)


def test_is_known_event_narrows_without_dropping_anything() -> None:
    """An event kind newer than this snapshot is still an event: flagged, never refused."""
    known = webhooks.parse(BODY)
    assert webhooks.is_known_event(known) is True
    alien = webhooks.parse('{"type":"alien","uuid":"x","sequence":3,"test":true}')
    assert webhooks.is_known_event(alien) is False
    # ...and the helpers still work on it, which is the whole point of returning it.
    assert webhooks.is_test_event(alien) is True
    assert webhooks.is_stale(alien, 2) is False
    assert webhooks.is_known_event({}) is False
    for kind in webhooks.KNOWN_EVENT_KINDS:
        assert webhooks.is_known_event({"type": kind}) is True
