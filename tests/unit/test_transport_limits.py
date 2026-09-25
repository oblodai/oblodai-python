"""What bounds a call: the per-attempt deadline, the body size cap, redirects, concurrency.

Every test here fails on the code as it was before the 1.3 hardening pass, which is the point:
a drip-feeding server used to hold a call open long past its ``timeout``, an unbounded body
used to be read into memory whole, and two threads correcting the clock used to fight.
"""

from __future__ import annotations

import threading
import time
from email.utils import formatdate
from typing import Any, Dict, List, Optional

import httpx
import pytest

from oblodai import Oblodai
from oblodai.aio import AsyncOblodai
from oblodai.core.engine import MAX_FILE_BYTES, MAX_JSON_BYTES, BodyReader, Send
from oblodai.core.errors import (
    ContractError,
    OblodaiError,
    ResponseTooLargeError,
    TransportError,
)
from oblodai.core.request import BuiltRequest
from oblodai.core.retry import RetryOptions
from oblodai.generated.signing import HEADER_TIMESTAMP
from tests.support.mock_http import MockHTTP, Scripted, api_error, ok
from tests.support.slow_http import (
    AsyncDripTransport,
    DripTransport,
    RecordingTransport,
    chunks_of,
)

NO_RETRY = RetryOptions(max_retries=0)
CREDS: Dict[str, Any] = {
    "public_id": "pk",
    "secret": "s",
    "base_url": "https://api.test",
    "retry": NO_RETRY,
    "env": {},
}


def _send(max_bytes: int = MAX_JSON_BYTES, timeout_ms: float = 1000.0) -> Send:
    request = BuiltRequest(
        url="https://api.test/v1/balance",
        method="POST",
        headers={},
        content=b"{}",
        request_uri="/v1/balance",
    )
    return Send(request, timeout_ms, max_bytes)


# --- the per-attempt deadline covers the whole read, not the first byte ----------------------


def test_a_drip_feeding_server_hits_the_attempt_timeout_instead_of_holding_the_call() -> None:
    """`httpx` times out per socket read; a server sending one chunk per tick never trips it."""
    transport = DripTransport(chunks_of(8 * 1024, 1024), delay=0.05)
    client = Oblodai(http_client=httpx.Client(transport=transport, timeout=10.0), **CREDS)
    started = time.monotonic()
    with pytest.raises(TransportError) as excinfo:
        client.account.get_balance(timeout=0.12)
    assert excinfo.value.code == "transport.timeout"
    assert time.monotonic() - started < 2.0  # not the 8 x 0.05 s the server wanted to take


async def test_the_async_client_bounds_the_whole_attempt_too() -> None:
    transport = AsyncDripTransport(chunks_of(8 * 1024, 1024), delay=0.05)
    client = AsyncOblodai(http_client=httpx.AsyncClient(transport=transport, timeout=10.0), **CREDS)
    started = time.monotonic()
    with pytest.raises(TransportError) as excinfo:
        await client.account.get_balance(timeout=0.12)
    assert excinfo.value.code == "transport.timeout"
    assert time.monotonic() - started < 2.0


def test_the_attempt_timeout_reaches_httpx_as_well() -> None:
    """The value is not just held in the engine: the socket gets it, so a stalled connect dies."""
    transport = RecordingTransport()
    client = Oblodai(http_client=httpx.Client(transport=transport), **CREDS)
    client.account.get_balance(timeout=1.234)
    timeout = transport.timeouts[0] or {}
    assert timeout.get("connect") == pytest.approx(1.234)
    assert timeout.get("read") == pytest.approx(1.234)


def test_the_call_deadline_caps_the_attempt_timeout() -> None:
    transport = RecordingTransport()
    client = Oblodai(
        http_client=httpx.Client(transport=transport), timeout=30, deadline=0.5, **CREDS
    )
    client.account.get_balance()
    timeout = transport.timeouts[0] or {}
    assert 0 < (timeout.get("read") or 0) <= 0.5


# --- the body size cap ------------------------------------------------------------------------


def test_the_body_reader_refuses_a_body_past_the_cap() -> None:
    reader = BodyReader(_send(max_bytes=1024), deadline=time.monotonic() + 60)
    reader.feed(b"x" * 1000, 200)
    with pytest.raises(ResponseTooLargeError) as excinfo:
        reader.feed(b"x" * 100, 200)
    assert excinfo.value.code == "sdk.response_too_large"
    assert isinstance(excinfo.value, ContractError)  # still catchable as a contract failure
    assert "1024" in str(excinfo.value)


def test_the_body_reader_refuses_a_body_that_arrives_after_the_deadline() -> None:
    reader = BodyReader(_send(timeout_ms=10), deadline=time.monotonic() - 1)
    with pytest.raises(TransportError) as excinfo:
        reader.feed(b"x", 200)
    assert excinfo.value.code == "transport.timeout"


def test_an_envelope_route_stops_reading_past_eight_mebibytes() -> None:
    """Not OOM: a proxy streaming an endless page must fail the call, not the process."""
    transport = DripTransport(chunks_of(MAX_JSON_BYTES + 2 * 1024 * 1024))
    client = Oblodai(http_client=httpx.Client(transport=transport), **CREDS)
    with pytest.raises(ResponseTooLargeError) as excinfo:
        client.account.get_balance()
    assert excinfo.value.code == "sdk.response_too_large"


def test_a_document_route_is_allowed_more_than_an_envelope_route() -> None:
    assert MAX_FILE_BYTES > MAX_JSON_BYTES
    transport = DripTransport(chunks_of(MAX_JSON_BYTES + 1024 * 1024))
    client = Oblodai(http_client=httpx.Client(transport=transport), **CREDS)
    document = client.documents.get_fees()
    assert len(document.content) == MAX_JSON_BYTES + 1024 * 1024


# --- redirects --------------------------------------------------------------------------------


def test_a_client_that_follows_a_redirect_behind_our_back_is_caught() -> None:
    """A signature is only valid for the URI it was signed for; a moved answer is not an answer.

    The SDK's own client never follows one, but a caller may inject a client that does.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.test":
            return httpx.Response(302, headers={"location": "https://elsewhere.test/v1/balance"})
        return httpx.Response(
            200, json={"state": 0, "result": {}}, headers={"content-type": "application/json"}
        )

    injected = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)
    client = Oblodai(http_client=injected, **CREDS)
    with pytest.raises(OblodaiError) as excinfo:
        client.account.get_balance()
    assert "redirect" in str(excinfo.value)
    assert "elsewhere.test" in str(excinfo.value)


def test_a_3xx_the_sdk_sees_itself_names_the_target() -> None:
    mock = MockHTTP(
        [Scripted(status=302, text="", headers={"location": "https://elsewhere.test/x"})]
    )
    client = Oblodai(http_client=mock.client, **CREDS)
    with pytest.raises(OblodaiError) as excinfo:
        client.account.get_balance()
    assert "https://elsewhere.test/x" in str(excinfo.value)


# --- clock skew under concurrency ---------------------------------------------------------------


def test_concurrent_calls_all_survive_an_hour_of_skew_with_one_correction() -> None:
    """Every thread shares one clock: a correction one call installs must not be clobbered."""
    server_now = int(time.time()) + 3600
    lock = threading.Lock()
    corrected: List[bool] = []

    def handle(request: httpx.Request) -> httpx.Response:
        signed_at = int(request.headers[HEADER_TIMESTAMP.lower()])
        with lock:
            if abs(signed_at - server_now) > 300:
                corrected.append(False)
                return httpx.Response(
                    401,
                    json={"error": {"code": "merchant.bad_signature", "retryable": False}},
                    headers={"date": formatdate(server_now, usegmt=True)},
                )
            corrected.append(True)
            return httpx.Response(200, json={"state": 0, "result": {"balance": {"merchant": []}}})

    client = Oblodai(
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        **{**CREDS, "retry": NO_RETRY},
    )
    failures: List[BaseException] = []

    def call() -> None:
        try:
            client.account.get_balance()
        except BaseException as err:  # the assertion below reports it
            failures.append(err)

    threads = [threading.Thread(target=call) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures, f"skew correction lost a call: {failures}"
    # The offset is learned once; later calls sign with it straight away.
    assert corrected.count(False) <= len(threads)
    assert client.transport.settings.clock.offset != 0


def test_reverting_a_correction_leaves_another_threads_correction_alone() -> None:
    from oblodai.core.clock import SkewCorrectingClock

    clock = SkewCorrectingClock(base=lambda: 1_000)
    clock.correct(60)
    assert clock.revert_if_unchanged(60, 0) is True
    assert clock.offset == 0
    clock.correct(90)  # another call's correction
    assert clock.revert_if_unchanged(60, 0) is False
    assert clock.offset == 90


# --- retry_after of the wrong shape must not crash mid-retry -----------------------------------


@pytest.mark.parametrize(
    "value", [True, "soon", None, [], {}, float("nan"), float("inf"), -5, "12", 12.5, 10**30]
)
def test_a_retry_after_of_any_shape_never_breaks_the_retry_loop(value: Any) -> None:
    """`retry_after` is attacker-adjacent JSON: any shape must land the SDK on a number or None."""
    mock = MockHTTP(
        [
            api_error(
                429, {"code": "request.rate_limited", "retryable": True, "retry_after": value}
            ),
            ok({"balance": {"merchant": []}}),
        ]
    )
    client = Oblodai(
        http_client=mock.client,
        **{
            **CREDS,
            "retry": RetryOptions(
                max_retries=1, base_delay_ms=1, max_delay_ms=2, max_retry_after_ms=5
            ),
        },
    )
    assert client.account.get_balance().balance.merchant == []
    assert len(mock.calls) == 2


def test_the_coerced_retry_after_is_never_negative_and_never_unbounded() -> None:
    from oblodai.core.errors import MAX_RETRY_AFTER_SECONDS, coerce_retry_after

    assert coerce_retry_after(-5) == 0.0
    assert coerce_retry_after(10**30) == MAX_RETRY_AFTER_SECONDS
    assert coerce_retry_after("  7 ") == 7.0
    junk: List[Any] = [True, False, None, "soon", [], {}, float("nan"), float("inf")]
    for value in junk:
        assert coerce_retry_after(value) is None


def test_a_retry_after_header_of_any_shape_is_bounded_too() -> None:
    from oblodai.core.envelope import parse_retry_after
    from oblodai.core.errors import MAX_RETRY_AFTER_SECONDS

    assert parse_retry_after("  30 ") == 30.0
    assert parse_retry_after("Sun, 06 Nov 2044 08:49:37 GMT") == MAX_RETRY_AFTER_SECONDS
    assert parse_retry_after("Sun, 06 Nov 1994 08:49:37 GMT") == 0.0
    junk: List[Optional[str]] = ["later", "", None, "\u0663\u0660", "-5", "9" * 400]
    for value in junk:
        parsed = parse_retry_after(value)
        assert parsed is None or 0 <= parsed <= MAX_RETRY_AFTER_SECONDS


# --- a bug in the SDK is a bug, not a retryable network failure -------------------------------


def test_a_programming_error_is_not_dressed_up_as_a_retryable_transport_failure() -> None:
    """`except Exception -> transport.network` would hide the bug AND re-send the request."""
    mock = MockHTTP([Scripted(raises=TypeError("a bug, not a socket")), ok({})])
    with pytest.raises(TypeError):
        Oblodai(
            http_client=mock.client, **{**CREDS, "retry": RetryOptions(max_retries=2)}
        ).account.get_balance()
    assert len(mock.calls) == 1


def test_a_real_socket_failure_still_becomes_a_transport_error() -> None:
    for boom in (httpx.ConnectError("refused"), OSError("connection reset")):
        mock = MockHTTP([Scripted(raises=boom), ok({"balance": {"merchant": []}})])
        client = Oblodai(
            http_client=mock.client,
            **{**CREDS, "retry": RetryOptions(max_retries=1, base_delay_ms=1, max_delay_ms=2)},
        )
        assert client.account.get_balance().balance.merchant == []
        assert len(mock.calls) == 2
