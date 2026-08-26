"""The guards a caller runs into before anything is signed, and the ones a hostile answer hits.

Each of these was reachable-but-unasserted before 1.3: flipping the guard off left the suite
green, which is the same as not having it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Tuple, cast

import pytest

from oblodai import Oblodai, compare_amounts
from oblodai.core.clock import MAX_PLAUSIBLE_OFFSET_SECONDS, SkewCorrectingClock
from oblodai.core.engine import EngineSettings
from oblodai.core.errors import (
    AmountError,
    ConfigError,
    ContractError,
    OblodaiError,
    api_error_from,
)
from oblodai.core.idempotency import MAX_IDEMPOTENCY_KEY_LENGTH
from oblodai.core.logger import redact
from oblodai.core.request import RESERVED_HEADERS, Credentials
from oblodai.core.retry import RetryOptions
from oblodai.helpers.money import MAX_AMOUNT_LENGTH
from tests.support.mock_http import MockHTTP, Scripted, ok

CREDS: Dict[str, Any] = {
    "public_id": "pk_test_1",
    "secret": "secret-1",
    "base_url": "https://api.test",
    "retry": RetryOptions(max_retries=0),
    "env": {},
}


def client(mock: MockHTTP, **overrides: Any) -> Oblodai:
    return Oblodai(http_client=mock.client, **{**CREDS, **overrides})


def create(api: Oblodai, **options: Any) -> Any:
    return api.payments.create({"amount": "1", "currency": "USDT"}, **options)


# --- idempotency keys -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["", "x" * (MAX_IDEMPOTENCY_KEY_LENGTH + 1), "has space", "tab\there", "nl\nhere", "kлюч"],
)
def test_an_unusable_idempotency_key_is_refused_before_signing(key: str) -> None:
    """The key is signed verbatim; a stray byte changes the MAC on one side only."""
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        create(client(mock), idempotency_key=key)
    assert excinfo.value.code == "sdk.bad_idempotency_key"
    assert excinfo.value.field == "idempotency_key"
    assert mock.calls == []


def test_a_key_of_exactly_the_maximum_length_is_accepted() -> None:
    mock = MockHTTP([ok({"uuid": "u"})])
    create(client(mock), idempotency_key="k" * MAX_IDEMPOTENCY_KEY_LENGTH)
    assert len(mock.calls[0].headers["idempotency-key"]) == MAX_IDEMPOTENCY_KEY_LENGTH


def test_a_key_on_a_route_the_core_does_not_deduplicate_is_refused() -> None:
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).account.balance(idempotency_key="k")
    assert excinfo.value.code == "sdk.idempotency_unsupported"
    assert mock.calls == []


# --- headers ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(RESERVED_HEADERS))
def test_a_caller_cannot_take_over_a_header_the_sdk_owns(name: str) -> None:
    """Case-insensitively: `x-signature` and `X-Signature` are the same header on the wire."""
    mock = MockHTTP([ok({"uuid": "u"})])
    create(client(mock, headers={name.upper(): "hijacked", name: "hijacked"}))
    assert mock.calls[0].headers.get(name) != "hijacked"


def test_a_caller_header_survives_when_it_collides_with_nothing() -> None:
    mock = MockHTTP([ok({"uuid": "u"})])
    create(client(mock, headers={"X-Trace": "t1"}))
    assert mock.calls[0].headers["x-trace"] == "t1"


@pytest.mark.parametrize("value", ["one\r\nX-Injected: yes", "line\nbreak", "nul\0byte", "héllo"])
def test_a_header_value_that_could_split_the_request_is_refused(value: str) -> None:
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        create(client(mock, headers={"X-Trace": value}))
    assert excinfo.value.code == "sdk.bad_header"
    assert mock.calls == []


def test_the_admin_token_goes_only_to_the_onboarding_routes() -> None:
    """It gates the whole gateway; every merchant route that saw it would be a place it leaks."""
    mock = MockHTTP([ok({"merchant_id": "m"}), ok({"uuid": "u"})])
    api = client(mock, admin_token="adm")
    api.merchants.create({"email": "a@b.c"})
    create(api)
    assert mock.calls[0].headers["x-admin-token"] == "adm"
    assert "x-admin-token" not in mock.calls[1].headers


# --- request bodies ---------------------------------------------------------------------------


def test_a_non_finite_float_in_a_body_is_named_instead_of_becoming_the_token_nan() -> None:
    """`json.dumps` renders NaN as the bare word NaN, which is not JSON and not an amount."""
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).payments.create(cast(Any, {"amount": float("nan"), "currency": "USDT"}))
    assert excinfo.value.code == "sdk.bad_body"
    assert mock.calls == []


def test_a_decimal_in_a_body_is_rendered_as_the_wire_string_not_a_type_error() -> None:
    mock = MockHTTP([ok({"uuid": "u"})])
    client(mock).payments.create(cast(Any, {"amount": Decimal("25.5"), "currency": "USDT"}))
    assert mock.calls[0].json["amount"] == "25.5"


def test_an_object_json_cannot_encode_names_itself() -> None:
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).payments.create(cast(Any, {"amount": object(), "currency": "USDT"}))
    assert "object" in str(excinfo.value)
    assert mock.calls == []


# --- money helpers ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["", "1.", ".5", "1.2.3", "x", "1e5", "٥", "1 000", "+1", "-", "9" * (MAX_AMOUNT_LENGTH + 1)],
)
def test_the_money_helpers_refuse_anything_that_is_not_a_decimal_string(bad: str) -> None:
    with pytest.raises(AmountError) as excinfo:
        compare_amounts(bad, "1")
    assert excinfo.value.code == "sdk.bad_amount"
    # Still a ValueError, so pre-1.3 `except ValueError` keeps working.
    assert isinstance(excinfo.value, ValueError)


def test_the_money_helpers_refuse_a_non_string() -> None:
    with pytest.raises(AmountError):
        compare_amounts(25, "1")  # type: ignore[arg-type]


def test_amounts_do_not_compare_the_way_their_strings_do() -> None:
    assert "10" < "9"  # the trap the helper exists to avoid
    assert compare_amounts("10", "9") == 1


# --- clock ------------------------------------------------------------------------------------


def test_an_implausible_server_date_is_ignored_rather_than_believed() -> None:
    """A proxy with a broken Date must not be able to push every signature out of the window."""
    clock = SkewCorrectingClock(base=lambda: 1_000_000)
    ok_offset = clock.observe_server_date("Sun, 06 Nov 1994 08:49:37 GMT")
    assert ok_offset is None or abs(ok_offset) <= MAX_PLAUSIBLE_OFFSET_SECONDS
    assert clock.observe_server_date("Fri, 31 Dec 9999 23:59:59 GMT") is None
    assert clock.observe_server_date("not a date") is None
    assert clock.observe_server_date(None) is None
    assert clock.offset == 0


# --- error envelopes of the wrong shape ---------------------------------------------------------


def test_each_envelope_field_is_decoded_on_its_own() -> None:
    error = api_error_from(
        400,
        cast(
            Any,
            {
                "code": "payment.bad_amount",
                "message": 12,
                "field": ["amount"],
                "request_id": {"x": 1},
                "retryable": "yes",
                "retry_after": "nonsense",
            },
        ),
    )
    assert error.code == "payment.bad_amount"
    assert error.message == "HTTP 400"
    assert error.field is None
    assert error.request_id is None
    assert error.retryable is False  # a non-boolean is not the core speaking
    assert error.retry_after is None


def test_an_envelope_without_a_usable_code_is_treated_as_no_envelope() -> None:
    error = api_error_from(503, cast(Any, {"code": "", "retryable": True}))
    assert error.synthetic is True
    assert error.retryable is True  # from the status, not from the body's claim


def test_a_deeply_nested_error_body_does_not_escape_as_a_recursion_error() -> None:
    mock = MockHTTP([Scripted(status=500, text="[" * 100_000 + "]" * 100_000)])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).account.balance()
    assert excinfo.value.synthetic is True


def test_a_deeply_nested_success_body_is_a_contract_error_not_a_crash() -> None:
    mock = MockHTTP([Scripted(status=200, text="[" * 100_000 + "]" * 100_000)])
    with pytest.raises(ContractError):
        client(mock).account.balance()


# --- secrets never render -----------------------------------------------------------------------


def test_no_secret_reaches_a_repr() -> None:
    settings = EngineSettings(
        base_url="https://api.test",
        user_agent="ua",
        credentials=Credentials("pk_live_1", "super-secret"),
        payout_credentials=Credentials("wk_live_1", "other-secret"),
        headers={"X-Trace": "t"},
        admin_token="adm-secret",
    )
    rendered = f"{settings!r} {settings.credentials!r} {settings.payout_credentials!r}"
    for secret in ("super-secret", "other-secret", "adm-secret"):
        assert secret not in rendered
    assert "pk_live_1" in rendered  # the public half stays, it is what identifies the key


def test_the_client_repr_names_the_key_but_not_the_secret() -> None:
    api = Oblodai(**{**CREDS, "secret": "super-secret"})
    assert "super-secret" not in repr(api)
    assert "pk_test_1" in repr(api)
    api.close()


def test_fields_are_redacted_before_a_caller_injected_logger_sees_them() -> None:
    """A caller's logger is not trusted to redact; the SDK does it on the way out."""
    seen: List[Tuple[str, Dict[str, Any]]] = []

    class Collecting:
        def _record(self, message: str, fields: Any = None) -> None:
            seen.append((message, dict(fields or {})))

        debug = info = warning = error = _record

    mock = MockHTTP([ok({"endpoint_id": "e", "url": "u", "secret": "whsec_live"})])
    api = client(mock, logger=Collecting())
    api.webhooks.register("https://x")
    for _, fields in seen:
        assert "whsec_live" not in repr(fields)
        for key, value in fields.items():
            if "secret" in key or "signature" in key or "token" in key:
                assert value == "[redacted]"


def test_a_payout_links_claim_url_is_redacted_like_the_token_it_embeds() -> None:
    """`claim_url` does not read like a secret and is one: it carries `claim_token` verbatim."""
    link: Dict[str, Any] = {
        "link_id": "l1",
        "amount": "25",
        "claim_token": "CLAIM-1",
        "claim_url": "https://pay.test/claim/CLAIM-1",
        "passcode": "0451",
        "items": [{"idx": 0, "result": {"claim_url": "https://pay.test/claim/CLAIM-2"}}],
    }

    fields: Dict[str, Any] = redact(link)

    assert fields["claim_url"] == "[redacted]"
    assert fields["claim_token"] == "[redacted]"
    assert fields["passcode"] == "[redacted]"
    assert fields["items"][0]["result"]["claim_url"] == "[redacted]"
    assert fields["amount"] == "25", "an ordinary field is left alone"
    assert "CLAIM-1" not in repr(fields) and "CLAIM-2" not in repr(fields)
    assert link["claim_url"] == "https://pay.test/claim/CLAIM-1", "the caller's own dict is intact"


# --- per-call headers ---------------------------------------------------------------------------


def test_a_per_call_header_wins_over_the_clients_own() -> None:
    mock = MockHTTP([ok({"uuid": "u"}), ok({"uuid": "u"})])
    api = client(mock, headers={"X-Trace": "client"})
    create(api, headers={"X-Trace": "call", "X-Extra": "e"})
    create(api)
    assert mock.calls[0].headers["x-trace"] == "call"
    assert mock.calls[0].headers["x-extra"] == "e"
    assert mock.calls[1].headers["x-trace"] == "client"  # the call-scoped one did not stick
    assert "x-extra" not in mock.calls[1].headers


def test_a_per_call_header_obeys_the_same_rules_as_a_client_one() -> None:
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        create(client(mock), headers={"X-Trace": "one\r\nX-Injected: yes"})
    assert excinfo.value.code == "sdk.bad_header"
    signed = MockHTTP([ok({"uuid": "u"})])
    create(client(signed), headers={"X-Signature": "hijacked"})
    assert signed.calls[0].headers["x-signature"] != "hijacked"
