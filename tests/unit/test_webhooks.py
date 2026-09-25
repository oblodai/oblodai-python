"""Webhook verification against real signed deliveries and against the rotation rules."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from oblodai import webhooks
from oblodai.core.errors import ConfigError, SignatureError, WebhookPayloadError
from oblodai.core.signing import sign_webhook
from oblodai.generated.signing import (
    HEADER_WEBHOOK_EVENT,
    HEADER_WEBHOOK_EVENT_ID,
    HEADER_WEBHOOK_ID,
    HEADER_WEBHOOK_SIGNATURE,
    HEADER_WEBHOOK_SIGNATURE_PREV,
    HEADER_WEBHOOK_TIMESTAMP,
    SKEW_SECONDS,
)
from tests.support.fixtures import load_webhook_samples, result_of

# The samples were delivered by the core's real dispatcher to the recorder, signed with the
# endpoint secret in force at that moment - the one returned by the rotate-secret call.
SAMPLES: List[Dict[str, Any]] = load_webhook_samples()
SECRET: str = result_of("POST /v1/webhooks/rotate-secret")["secret"]


@pytest.mark.parametrize(
    "index",
    range(len(SAMPLES)),
    ids=[s["headers"][HEADER_WEBHOOK_EVENT] + f"#{i}" for i, s in enumerate(SAMPLES)],
)
def test_verifies_every_recorded_delivery(index: int) -> None:
    sample = SAMPLES[index]
    raw = sample.get("raw") or json.dumps(sample["body"])
    ts = int(sample["headers"][HEADER_WEBHOOK_TIMESTAMP])

    delivery = webhooks.verify_delivery(raw, sample["headers"], secret=SECRET, now=ts)
    assert delivery.event["uuid"] == sample["body"]["uuid"]
    assert delivery.id == sample["headers"][HEADER_WEBHOOK_ID]
    assert delivery.event_type == sample["headers"][HEADER_WEBHOOK_EVENT]
    assert delivery.event["type"] == sample["body"]["type"]
    assert isinstance(delivery.event["sequence"], int)
    # Rehearsal deliveries (`webhooks.test`, sandbox) are signed like live ones and say so.
    assert delivery.is_test is (sample["body"].get("test") is True)
    assert delivery.is_test is (sample["headers"].get("X-Webhook-Test") == "true")
    assert webhooks.is_test_event(delivery.event) is delivery.is_test
    # The generated tables know every event the core really sends, and its model parses the body.
    kind = webhooks.WEBHOOK_EVENTS[sample["headers"][HEADER_WEBHOOK_EVENT]]
    assert kind == delivery.event["type"]
    assert webhooks.is_known_event(delivery.event)
    assert isinstance(webhooks.to_model(delivery.event), webhooks.WEBHOOK_MODELS[kind])

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
        HEADER_WEBHOOK_TIMESTAMP.lower(): str(TS),
        HEADER_WEBHOOK_SIGNATURE.lower(): sign_webhook("whsec", TS, BODY),
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
        webhooks.verify(BODY, {HEADER_WEBHOOK_SIGNATURE.lower(): "aa"}, secret="whsec")


def test_rejects_stale_deliveries_unless_tolerance_is_disabled() -> None:
    late = TS + SKEW_SECONDS + 1
    with pytest.raises(SignatureError, match="outside"):
        webhooks.verify(BODY, headers(), secret="whsec", now=late)
    event = webhooks.verify(BODY, headers(), secret="whsec", now=late, tolerance_sec=0)
    assert event["uuid"] == "u1"


def test_verifies_during_a_rotation_via_the_prev_header_or_previous_secret() -> None:
    rotated = headers(
        **{
            HEADER_WEBHOOK_SIGNATURE.lower(): sign_webhook("new", TS, BODY),
            HEADER_WEBHOOK_SIGNATURE_PREV.lower(): sign_webhook("old", TS, BODY),
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
    # Only `type` is required of every body; a known kind also needs its object's id field
    # (WEBHOOK_ID_FIELDS: a conversion's is `id`, not `uuid`).
    for body in ("<html/>", '{"uuid":"x"}', "[1,2]", '{"type":"payment","id":"x"}'):
        with pytest.raises(WebhookPayloadError) as excinfo:
            webhooks.parse(body)
        assert excinfo.value.code == "webhook.bad_payload"
        assert not isinstance(excinfo.value, SignatureError)


def test_an_unknown_kind_needs_no_uuid_or_id() -> None:
    """Which field identifies an object is known only for the contract's kinds: a newer kind keyed
    otherwise is still delivered, and object_id() does not guess its id."""
    event = webhooks.parse(b'{"type":"refund","refund_id":"r1","sequence":3}')
    assert event["type"] == "refund"
    assert webhooks.is_known_event(event) is False
    assert webhooks.object_id(event) is None
    assert webhooks.is_stale(event, 3) is True


def test_object_id_reads_the_field_the_contract_names_for_the_kind() -> None:
    assert set(webhooks.WEBHOOK_ID_FIELDS) == set(webhooks.KNOWN_EVENT_KINDS)
    for kind, field in webhooks.WEBHOOK_ID_FIELDS.items():
        event = webhooks.parse(json.dumps({"type": kind, field: "obj-1"}))
        assert webhooks.object_id(event) == "obj-1", kind
    conversion = webhooks.parse('{"type":"conversion","id":"c1","uuid":"not-this-one"}')
    assert webhooks.object_id(conversion) == "c1"
    assert webhooks.object_id({"type": "payment"}) is None


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
        webhooks.verify(
            BODY, headers(**{HEADER_WEBHOOK_TIMESTAMP.lower(): "later"}), secret="whsec"
        )


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
    stale_and_forged = headers(**{HEADER_WEBHOOK_TIMESTAMP.lower(): str(TS - 100_000)})
    with pytest.raises(SignatureError) as excinfo:
        webhooks.verify(BODY, stale_and_forged, secret="whsec", now=TS)
    assert excinfo.value.code == "webhook.bad_signature"


def test_a_signature_header_may_be_padded_or_uppercase_but_not_0x_prefixed() -> None:
    good = sign_webhook("whsec", TS, BODY)
    assert webhooks.verify(
        BODY, headers(**{HEADER_WEBHOOK_SIGNATURE.lower(): f"  {good} "}), secret="whsec", now=TS
    )
    assert webhooks.verify(
        BODY, headers(**{HEADER_WEBHOOK_SIGNATURE.lower(): good.upper()}), secret="whsec", now=TS
    )
    with pytest.raises(SignatureError, match="missing"):
        webhooks.verify(
            BODY, headers(**{HEADER_WEBHOOK_SIGNATURE.lower(): f"0x{good}"}), secret="whsec", now=TS
        )


def test_a_non_ascii_digit_timestamp_is_not_a_number() -> None:
    """`int("\u0661\u0662\u0663")` parses Arabic-Indic digits; the core never wrote those."""
    with pytest.raises(SignatureError, match="not an integer"):
        webhooks.verify(
            BODY,
            headers(**{HEADER_WEBHOOK_TIMESTAMP.lower(): "\u0661\u0662\u0663"}),
            secret="whsec",
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
        HEADER_WEBHOOK_TIMESTAMP.lower(): str(TS),
        HEADER_WEBHOOK_SIGNATURE.lower(): sign_webhook("whsec", TS, broken),
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


def test_resend_is_deduplicated_by_the_event_id_not_the_delivery_id() -> None:
    """A resend is a new DELIVERY of a state the receiver may already have handled.

    `POST /v1/payment/resend` queues a fresh delivery with a new `X-Webhook-Id` and a deliberately
    HIGHER `sequence` — deliberately, because a lower number may be discarded as a straggler and a
    resend has to be able to correct a reorg reversal. So neither of the two rules this SDK used to
    teach (dedupe by id, skip by sequence) drops it, and a fulfilment that was not idempotent by
    (uuid, status) shipped the goods twice. `X-Webhook-Event-Id` is the key that answers it.
    """
    body = {"type": "payment", "uuid": "inv-1", "status": "paid", "sequence": 7}
    ts = 1_800_000_000
    raw_first = json.dumps(body)
    raw_resend = json.dumps({**body, "sequence": 42})

    def headers(raw: str, delivery_id: str, event_id: str) -> Dict[str, Any]:
        return {
            HEADER_WEBHOOK_TIMESTAMP: str(ts),
            HEADER_WEBHOOK_SIGNATURE: sign_webhook(SECRET, ts, raw.encode()),
            HEADER_WEBHOOK_EVENT: "invoice.paid",
            HEADER_WEBHOOK_ID: delivery_id,
            HEADER_WEBHOOK_EVENT_ID: event_id,
        }

    state = "5d9f1c0e-0000-5000-8000-000000000001"
    first = webhooks.verify_delivery(
        raw_first, headers(raw_first, "d-1", state), secret=SECRET, now=ts
    )
    resend = webhooks.verify_delivery(
        raw_resend, headers(raw_resend, "d-2", state), secret=SECRET, now=ts
    )

    assert first.id != resend.id, "a resend is a different delivery"
    assert not webhooks.is_stale(resend.event, last_processed_sequence=7), "a resend is never stale"
    assert first.event_id == resend.event_id == state, "the state id is what repeats"


def test_event_id_is_absent_on_an_older_core() -> None:
    """A core that predates the header must not make the field lie: it is None, and the receiver
    falls back to (uuid, status) idempotency."""
    body = {"type": "payment", "uuid": "inv-2", "status": "paid", "sequence": 1}
    ts = 1_800_000_000
    raw = json.dumps(body)
    delivery = webhooks.verify_delivery(
        raw,
        {
            HEADER_WEBHOOK_TIMESTAMP: str(ts),
            HEADER_WEBHOOK_SIGNATURE: sign_webhook(SECRET, ts, raw.encode()),
            HEADER_WEBHOOK_EVENT: "invoice.paid",
            HEADER_WEBHOOK_ID: "d-9",
        },
        secret=SECRET,
        now=ts,
    )
    assert delivery.event_id is None


def test_conversion_events_are_known_and_parse_to_their_model() -> None:
    """``conversion.completed`` / ``conversion.refunded`` come from the contract like every kind."""
    from oblodai import ConversionWebhook
    from tests.support.samples import sample

    assert "conversion" in webhooks.KNOWN_EVENT_KINDS
    assert webhooks.WEBHOOK_EVENTS["conversion.completed"] == "conversion"
    assert webhooks.WEBHOOK_EVENTS["conversion.refunded"] == "conversion"
    assert webhooks.WEBHOOK_MODELS["conversion"] is ConversionWebhook
    body = sample(ConversionWebhook, type="conversion", id="c1", status="completed")
    assert "uuid" not in body, "a conversion is identified by id, not uuid"
    # Signed and verified like any delivery - no uuid is not a bad payload.
    signed = {
        HEADER_WEBHOOK_TIMESTAMP.lower(): str(TS),
        HEADER_WEBHOOK_SIGNATURE.lower(): sign_webhook("whsec", TS, json.dumps(body)),
    }
    event = webhooks.verify(json.dumps(body), signed, secret="whsec", now=TS)
    assert webhooks.is_known_event(event) is True
    model = webhooks.to_model(event)
    assert isinstance(model, ConversionWebhook) and model.id == "c1"


def test_to_model_leaves_an_unknown_kind_alone_and_rejects_a_broken_known_one() -> None:
    assert webhooks.to_model({"type": "alien", "uuid": "x"}) is None
    assert webhooks.to_model({}) is None
    with pytest.raises(WebhookPayloadError, match="PaymentWebhook"):
        webhooks.to_model({"type": "payment"})


def test_every_known_kind_has_a_model_and_an_event() -> None:
    assert set(webhooks.WEBHOOK_MODELS) == set(webhooks.KNOWN_EVENT_KINDS)
    assert set(webhooks.WEBHOOK_EVENTS.values()) == set(webhooks.KNOWN_EVENT_KINDS)
