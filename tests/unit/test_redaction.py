"""Bearer secrets never reach what the SDK shows people: hooks, error messages, reprs, logs.

The claim token of ``/v1/claim/{token}`` and ``/v1/aml/{token}`` and a signed document link's
``sig``/``exp`` travel in the URL; a caller's proxy credentials travel in headers; the CLI device
flow's ``device_code`` travels in a model. Each one used to show up somewhere.
"""

from __future__ import annotations

from typing import Any, List

import httpx
import pytest

from oblodai import Hooks, OblodaiError
from oblodai.core.hooks import RequestInfo, ResponseInfo
from oblodai.core.logger import redact
from oblodai.core.request import build_request
from oblodai.generated.models import CLIDeviceAuthorization
from oblodai.generated.routes import ROUTES
from tests.support.clients import make_client

TOKEN = "CLAIMTOKEN-ONE-TIME"
SIG = "SIGVALUE0123"


def _capture(handler: Any, **kw: Any) -> Any:
    seen: List[Any] = []
    hooks = Hooks(on_request=seen.append, on_response=seen.append)
    return make_client(handler, hooks=hooks, **kw), seen


def test_hooks_see_the_route_with_the_claim_token_and_proxy_credentials_masked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"code": "payout_link.not_found", "retryable": False}}
        )

    client, seen = _capture(
        handler,
        headers={
            "Authorization": "Bearer PROXY-TOKEN",
            "x-api-key": "PROXY-KEY",
            "X-Claim-Passcode": "PASSCODE-1",
            "X-Trace": "t-1",
        },
    )
    with pytest.raises(OblodaiError) as excinfo:
        client.payout_links.get_payout_claim(TOKEN)
    request = seen[0]
    assert isinstance(request, RequestInfo)
    assert TOKEN not in request.url and request.url.endswith("/v1/claim/[redacted]")
    rendered = f"{request!r} {dict(request.headers)!r} {seen[1]!r} {excinfo.value!r}"
    for secret in (TOKEN, "PROXY-TOKEN", "PROXY-KEY", "PASSCODE-1"):
        assert secret not in rendered
    assert request.headers["X-Trace"] == "t-1"
    assert isinstance(seen[1], ResponseInfo)


def test_a_signed_document_link_shows_no_sig_or_exp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["sig"] == SIG  # the wire keeps the real value
        return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    client, seen = _capture(handler)
    client.documents.get_signed("invoice", "i-1", exp=1900000000, sig=SIG, lang="en")
    url = seen[0].url
    assert SIG not in url and "1900000000" not in url
    assert "sig=[redacted]" in url and "exp=[redacted]" in url and "lang=en" in url


def test_error_messages_carry_no_claim_token() -> None:
    def too_big(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (9 * 1024 * 1024))

    with pytest.raises(OblodaiError) as excinfo:
        make_client(too_big).payout_links.get_payout_claim(TOKEN)
    assert "exceeds" in str(excinfo.value) and TOKEN not in str(excinfo.value)

    def broken(request: httpx.Request) -> httpx.Response:
        # An HTTP library that names the URL in its error text.
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(OblodaiError) as excinfo:
        make_client(broken, retry=None).payout_links.get_payout_claim(TOKEN)
    assert "cannot reach" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": f"https://evil.test/v1/claim/{TOKEN}"})

    with pytest.raises(OblodaiError) as excinfo:
        make_client(redirect).payout_links.get_payout_claim(TOKEN)
    assert "evil.test" in str(excinfo.value) and TOKEN not in str(excinfo.value)


def test_a_built_request_repr_shows_neither_the_signature_nor_the_token() -> None:
    from oblodai.core.request import Credentials

    request = build_request(
        base_url="https://api.test",
        route=ROUTES["getPayoutClaim"],
        body=b"",
        ts=1,
        user_agent="ua",
        path_params={"token": TOKEN},
        credentials=Credentials("p", "SECRET-XYZ"),
    )
    assert TOKEN in request.url  # the wire needs it
    assert TOKEN not in repr(request) and "SECRET-XYZ" not in repr(request)


def test_the_device_code_is_redacted_in_models_and_logs() -> None:
    model = CLIDeviceAuthorization.from_dict(
        {
            "device_code": "SECRET-DEVICE-CODE-123",
            "expires_in": 600,
            "interval": 5,
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://my.oblodai.com/cli",
            "verification_uri_complete": "https://my.oblodai.com/cli?code=ABCD-EFGH",
        }
    )
    assert "SECRET-DEVICE-CODE-123" not in repr(model)
    assert "SECRET-DEVICE-CODE-123" not in repr(redact(model.to_dict()))
    assert "ABCD-EFGH" in repr(model)  # the user code is meant to be shown
    assert redact({"X-Api-Key": "k", "api_key": {"secret": "s"}}) == {
        "X-Api-Key": "[redacted]",
        "api_key": "[redacted]",
    }
