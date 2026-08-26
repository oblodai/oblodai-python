"""The paths where a wrong retry would move money twice, plus request construction rules."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from oblodai import Oblodai
from oblodai.core.errors import ConfigError, OblodaiError, TransportError
from oblodai.core.retry import RetryOptions
from tests.support.mock_http import MockHTTP, Scripted, api_error, html, ok

CREDS: Dict[str, Any] = {
    "public_id": "pk",
    "secret": "s",
    "base_url": "https://api.test",
    "retry": RetryOptions(base_delay_ms=1, max_delay_ms=2),
    "env": {},
}


def client(mock: MockHTTP, **overrides: Any) -> Oblodai:
    options: Dict[str, Any] = {**CREDS, **overrides}
    return Oblodai(http_client=mock.client, **options)


# --- paths that could double-spend ---------------------------------------------------------


def test_rejects_a_caller_key_on_a_route_the_core_does_not_deduplicate() -> None:
    mock = MockHTTP([ok({})])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).payouts.approve("p1", idempotency_key="k1")
    assert excinfo.value.code == "sdk.idempotency_unsupported"
    assert mock.calls == []


def test_never_re_sends_an_unsafe_write_after_a_proxy_503_without_an_envelope() -> None:
    mock = MockHTTP([html(503), ok({})])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).payouts.approve("p1")
    error = excinfo.value
    assert error.http_status == 503
    assert error.synthetic is True
    assert error.retryable is True
    assert len(mock.calls) == 1


def test_retries_a_read_route_after_a_proxy_502_and_honours_retry_after() -> None:
    mock = MockHTTP([html(502), html(504, {"retry-after": "0"}), ok({"balance": {"merchant": []}})])
    client(mock).account.balance()
    assert len(mock.calls) == 3

    capped = MockHTTP([html(429, {"retry-after": "120"})])
    with pytest.raises(OblodaiError) as excinfo:
        client(capped, retry=RetryOptions(max_retries=0)).account.balance()
    assert excinfo.value.retry_after == 120


def test_retries_an_enveloped_retryable_error_on_an_unsafe_write() -> None:
    # The core answered, so it did not perform the operation.
    mock = MockHTTP(
        [
            api_error(409, {"code": "payout.funds_maturing", "retryable": True, "retry_after": 0}),
            ok({"uuid": "p"}),
        ]
    )
    client(mock).payouts.approve("p1")
    assert len(mock.calls) == 2


# --- lazy lists ----------------------------------------------------------------------------


def test_a_list_requests_nothing_until_it_is_consumed() -> None:
    mock = MockHTTP([api_error(404, {"code": "payment.not_found", "retryable": False})])
    api = client(mock)
    pending = api.payments.history()
    assert mock.calls == []
    with pytest.raises(OblodaiError) as excinfo:
        pending.first()
    assert excinfo.value.code == "payment.not_found"
    assert len(mock.calls) == 1


def test_an_unconsumed_failing_list_is_inert() -> None:
    mock = MockHTTP([])
    api = client(mock)
    api.payments.history()  # never consumed: no request, no error, nothing to clean up
    api.payouts.history({"limit": 5})
    assert mock.calls == []


def test_refuses_a_caller_idempotency_key_on_a_list_route_instead_of_dropping_it() -> None:
    """A silent drop leaves the caller believing the call was deduplicated. It was not."""
    mock = MockHTTP([])
    with pytest.raises(ConfigError) as excinfo:
        client(mock).payouts.history({}, idempotency_key="k")
    assert excinfo.value.code == "sdk.idempotency_unsupported"
    assert excinfo.value.field == "idempotency_key"
    assert mock.calls == []
    # ... and paging still sends no key of its own: one key across pages would make the core
    # replay page 1 forever.
    paged = MockHTTP(
        [
            ok(
                {
                    "items": [{"uuid": "a"}],
                    "paginate": {"total": 2, "per_page": 1, "offset": 0, "has_pages": True},
                }
            ),
            ok(
                {
                    "items": [{"uuid": "b"}],
                    "paginate": {"total": 2, "per_page": 1, "offset": 1, "has_pages": False},
                }
            ),
        ]
    )
    assert len(client(paged).payouts.history({"limit": 1}).all()) == 2
    assert all("idempotency-key" not in call.headers for call in paged.calls)


# --- clock skew ----------------------------------------------------------------------------


def _far_date() -> Dict[str, str]:
    import time
    from email.utils import formatdate

    return {"date": formatdate(time.time() + 4000, usegmt=True)}


def test_ignores_the_date_header_on_a_401_that_is_not_a_signature_failure() -> None:
    mock = MockHTTP(
        [api_error(401, {"code": "auth.ip_not_allowed", "retryable": False}, _far_date())]
    )
    with pytest.raises(OblodaiError) as excinfo:
        client(mock, retry=RetryOptions(max_retries=0)).account.balance()
    assert excinfo.value.code == "auth.ip_not_allowed"
    assert len(mock.calls) == 1


def test_reverts_the_correction_when_the_re_signed_attempt_is_still_rejected() -> None:
    import time

    bad = api_error(401, {"code": "merchant.bad_signature", "retryable": False}, _far_date())
    mock = MockHTTP([bad, bad, ok({"balance": {"merchant": []}})])
    api = client(mock, retry=RetryOptions(max_retries=0))
    with pytest.raises(OblodaiError):
        api.account.balance()
    api.account.balance()
    # One bad `Date` cannot wedge the client: the third call signs with the local clock again.
    assert abs(int(mock.calls[2].headers["x-timestamp"]) - int(time.time())) < 5


# --- request construction ------------------------------------------------------------------


def test_keeps_a_path_prefix_on_the_base_url_and_signs_the_full_path() -> None:
    mock = MockHTTP([ok({"balance": {"merchant": []}})])
    client(mock, base_url="https://gw.corp/oblodai/").account.balance()
    assert mock.calls[0].url == "https://gw.corp/oblodai/v1/balance"


def test_drops_caller_headers_that_collide_with_signed_headers() -> None:
    mock = MockHTTP([ok({"balance": {"merchant": []}})])
    client(mock, headers={"x-signature": "zz", "X-Trace": "t1"}).account.balance()
    assert mock.calls[0].headers["x-signature"] != "zz"
    assert mock.calls[0].headers["x-trace"] == "t1"


def test_refuses_path_parameters_that_would_rewrite_the_url() -> None:
    api = client(MockHTTP([]))
    for bad in ("..", ".", "a/b", ""):
        with pytest.raises(ConfigError) as excinfo:
            api.payments.public_view(bad)
        assert excinfo.value.code == "sdk.bad_path_param"


def test_percent_encodes_path_parameters() -> None:
    mock = MockHTTP([ok({"uuid": "x"})])
    client(mock).payments.public_view("a b?c")
    assert mock.calls[0].url == "https://api.test/v1/pay/a%20b%3Fc"


def test_sends_uuid_for_document_reports_keyed_by_batch_or_link_id() -> None:
    mock = MockHTTP(
        [Scripted(status=200, text="%PDF", headers={"content-type": "application/pdf"})]
    )
    document = client(mock).documents.batch_report("b-1", {"format": "csv"})
    assert mock.calls[0].query("uuid") == "b-1"
    assert mock.calls[0].query("format") == "csv"
    assert document.content_type == "application/pdf"
    assert document.content == b"%PDF"


def test_reads_the_filename_from_content_disposition() -> None:
    mock = MockHTTP(
        [
            Scripted(
                status=200,
                text="%PDF",
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="statement.pdf"',
                },
            )
        ]
    )
    assert client(mock).documents.statement().filename == "statement.pdf"


def test_serializes_the_body_compactly_and_signs_exactly_those_bytes() -> None:
    mock = MockHTTP([ok({"uuid": "u"})])
    client(mock).payments.create({"amount": "1", "currency": "USDT", "additional_data": "тест"})
    body = mock.calls[0].body
    assert body is not None
    assert " " not in body.replace("тест", "")
    assert json.loads(body)["additional_data"] == "тест"


# --- deadline, redirects, serialization ------------------------------------------------------


def test_stops_retrying_when_the_overall_deadline_would_be_exceeded() -> None:
    mock = MockHTTP(
        [
            api_error(503, {"code": "db.unavailable", "retryable": True, "retry_after": 2}),
            ok({}),
        ]
    )
    with pytest.raises(TransportError) as excinfo:
        client(mock, deadline_ms=100).account.balance()
    assert excinfo.value.code == "transport.deadline"
    assert len(mock.calls) == 1


def test_names_the_redirect_target_instead_of_a_bare_envelope_error() -> None:
    mock = MockHTTP(
        [Scripted(status=301, text="", headers={"location": "https://www.api.test/v1/balance"})]
    )
    with pytest.raises(OblodaiError) as excinfo:
        client(mock, retry=RetryOptions(max_retries=0)).account.balance()
    assert excinfo.value.http_status == 301
    assert "redirect" in str(excinfo.value)
    assert "www.api.test" in str(excinfo.value)


def test_serializes_errors_without_the_raw_body_and_keeps_the_message() -> None:
    mock = MockHTTP(
        [
            api_error(
                400,
                {"code": "payment.below_minimum", "message": "too small", "retryable": False},
            )
        ]
    )
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).payments.create({"amount": "0", "currency": "USDT"})
    error = excinfo.value
    payload = error.to_dict()
    assert payload["code"] == "payment.below_minimum"
    assert payload["message"] == "too small"
    assert payload["http_status"] == 400
    assert "raw" not in payload
    assert "raw" not in repr(error)


def test_a_success_envelope_that_is_not_one_raises_a_contract_error() -> None:
    mock = MockHTTP([Scripted(status=200, body={"unexpected": True})])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).account.balance()
    assert excinfo.value.code == "sdk.bad_envelope"


def test_an_oversized_idempotent_replay_is_reported_not_returned() -> None:
    mock = MockHTTP([ok({"idempotent_replay": True, "detail": "response too large"})])
    with pytest.raises(OblodaiError) as excinfo:
        client(mock).payments.create({"amount": "1", "currency": "USDT"})
    assert excinfo.value.code == "sdk.bad_envelope"
    assert "already processed" in str(excinfo.value)
