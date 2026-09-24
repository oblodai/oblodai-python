"""The shared conformance suite every Oblodai SDK runs (backend ``tools/sdkgen/conformance``).

Scenarios are read from ``$SDKGEN_CONFORMANCE``, else from ``tools/sdkgen/conformance`` of the
backend checkout the drift check uses (``$OBLODAI_BACKEND``, else ``../oblodai-backend``).
Signing vectors are not in the scenario files: each suite names the backend ``openapi.json`` and a
pointer into its ``x-oblodai-signing``, and the vectors are read from there.

Every call scenario runs on the sync and on the async client over ``httpx.MockTransport``; retry
pauses are recorded instead of slept.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect
import json
import os
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx
import pytest

import oblodai.generated.resources as generated
from oblodai import AsyncOblodai, Oblodai
from oblodai.core import atransport, transport
from oblodai.core.errors import OblodaiError, SignatureError, WebhookPayloadError
from oblodai.core.signing import canonical_string, sign_request, sign_webhook
from oblodai.webhooks import verify
from scripts.check_generated import backend_root
from tests.support.clients import PUBLIC_ID, SECRET

_EXPLICIT = os.environ.get("SDKGEN_CONFORMANCE")
CONFORMANCE = Path(_EXPLICIT) if _EXPLICIT else backend_root() / "tools" / "sdkgen" / "conformance"

if not CONFORMANCE.is_dir():
    if _EXPLICIT or os.environ.get("OBLODAI_BACKEND"):
        raise RuntimeError(f"conformance suite not found at {CONFORMANCE}")
    pytest.skip(
        f"conformance suite not found at {CONFORMANCE}; set OBLODAI_BACKEND or SDKGEN_CONFORMANCE",
        allow_module_level=True,
    )


def _suite(name: str) -> Dict[str, Any]:
    data: Dict[str, Any] = json.loads((CONFORMANCE / f"{name}.json").read_text("utf-8"))
    return data


def _pointer(doc: Any, pointer: str) -> Any:
    cur = doc
    for part in pointer.lstrip("/").split("/"):
        cur = cur[part.replace("~1", "/").replace("~0", "~")]
    return cur


def _source(suite: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """The spec's ``x-oblodai-signing`` and the vectors the suite points at."""
    src = suite["source"]
    spec = json.loads((CONFORMANCE / src["spec"]).read_text("utf-8"))
    vectors: List[Dict[str, Any]] = _pointer(spec, src["pointer"])
    return spec["x-oblodai-signing"], vectors


def _cases(name: str) -> List[Any]:
    suite = _suite(name)
    signing, vectors = _source(suite)
    return [
        pytest.param(check, vector, signing, id=f"{check['name']}#{i}")
        for check in suite["checks"]
        for i, vector in enumerate(vectors)
    ]


# -- signing -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("check", "vector", "signing"), _cases("signing"))
def test_request_signing(check: Dict[str, Any], vector: Dict[str, Any], signing: Any) -> None:
    key = vector["idempotency_key"] or None
    args = (vector["ts"], vector["method"], vector["request_uri"], vector["body"], key)
    if check["kind"] == "request_canonical":
        assert canonical_string(*args) == vector["canonical"]
    else:
        assert check["kind"] == "request_signature"
        assert sign_request(vector["secret"], *args) == vector["signature"]


@pytest.mark.parametrize(("check", "vector", "signing"), _cases("webhook"))
def test_webhook(check: Dict[str, Any], vector: Dict[str, Any], signing: Dict[str, Any]) -> None:
    secret, ts, payload = vector["secret"], vector["ts"], vector["payload"]
    if check["kind"] == "webhook_signature":
        assert sign_webhook(secret, ts, payload) == vector["signature"]
        return
    assert check["kind"] == "webhook_verify"
    skew = int(signing["skew_seconds"])
    offset = {"skew": skew, "skew+1": skew + 1}.get(check["now_from_ts"], check["now_from_ts"])
    signature = vector["signature"]
    if check["mutate"] == "payload":
        payload = payload + " "
    elif check["mutate"] == "signature":
        signature = ("0" if signature[0] != "0" else "1") + signature[1:]
    headers = {"X-Webhook-Timestamp": str(ts), "X-Webhook-Signature": signature}
    if check["expect"] == "ok":
        # The vectors sign bare payloads, not whole events: verify() gets past the MAC and the
        # freshness window and only then may refuse to parse - that refusal still is a pass.
        with contextlib.suppress(WebhookPayloadError):
            verify(payload, headers, secret=secret, tolerance_sec=skew, now=ts + int(offset))
        return
    with pytest.raises(SignatureError) as caught:
        verify(payload, headers, secret=secret, tolerance_sec=skew, now=ts + int(offset))
    assert caught.value.code == "webhook." + check["expect"]


# -- calls -------------------------------------------------------------------------------------


def _operations() -> Dict[str, Tuple[str, str]]:
    """``operationId`` -> (generated resource class, method) - read from the generated source."""
    tree = ast.parse(inspect.getsource(generated))
    out: Dict[str, Tuple[str, str]] = {}
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Subscript)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "ROUTES"
                    and isinstance(node.slice, ast.Constant)
                ):
                    out[str(node.slice.value)] = (cls.name, fn.name)
    return out


OPERATIONS = _operations()


def _bound(client: Any, operation: str) -> Any:
    cls_name, method = OPERATIONS[operation]
    for resource in vars(client).values():
        if type(resource).__name__.removeprefix("Async") == cls_name:
            return getattr(resource, method)
    raise AssertionError(f"no resource on the client serves {operation}")


class Script:
    """Replays the scenario's responses and records what the SDK sent and how long it paused."""

    def __init__(self, responses: List[Dict[str, Any]]) -> None:
        self.queue = list(responses)
        self.requests: List[httpx.Request] = []
        self.delays_ms: List[float] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.queue:
            raise AssertionError(f"unscripted request {request.method} {request.url}")
        nxt = self.queue.pop(0)
        if nxt.get("transport_error") == "timeout":
            raise httpx.ReadTimeout("scripted timeout", request=request)
        headers = dict(nxt.get("headers") or {})
        if "json" in nxt:
            headers.setdefault("content-type", "application/json")
            return httpx.Response(nxt["status"], content=json.dumps(nxt["json"]), headers=headers)
        headers.setdefault("content-type", "text/html")
        return httpx.Response(nxt["status"], content=b"<html>proxy</html>", headers=headers)

    def sleep(self, seconds: float) -> None:
        self.delays_ms.append(seconds * 1000.0)

    async def asleep(self, seconds: float) -> None:
        self.delays_ms.append(seconds * 1000.0)


class _Time:
    def __init__(self, real: Any, sleep: Any) -> None:
        self._real, self.sleep = real, sleep

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def _check(
    scenario: Dict[str, Any], script: Script, result: Any, error: Optional[BaseException]
) -> None:
    expect = scenario["expect"]
    assert len(script.requests) == expect["requests"], [str(r.url) for r in script.requests]
    keys = [r.headers.get("idempotency-key") for r in script.requests]
    if expect.get("idempotency_key") == "absent":
        assert keys == [None] * len(keys)
    elif expect.get("idempotency_key") == "present":
        assert all(keys)
    if expect.get("same_idempotency_key"):
        assert keys[0] and len(set(keys)) == 1, keys
    if "delays_ms" in expect:
        assert script.delays_ms == expect["delays_ms"]
    for name, want in (expect.get("request_body_field") or {}).items():
        assert json.loads(script.requests[-1].content)[name] == want
    if "error_code" in expect:
        assert isinstance(error, OblodaiError), error
        assert error.code == expect["error_code"]
        return
    if error is not None:
        raise error
    for name, want in (expect.get("result_field") or {}).items():
        assert _plain(getattr(result, name)) == want


def _scenarios() -> List[Any]:
    return [
        pytest.param(s, id=f"{name}/{s['name']}")
        for name in ("retry", "money", "forward_compat")
        for s in _suite(name)["scenarios"]
    ]


def _args(scenario: Dict[str, Any]) -> Tuple[Any, ...]:
    args: Mapping[str, Any] = scenario["call"]["args"]
    return (dict(args),) if args else ()


@pytest.mark.parametrize("scenario", _scenarios())
def test_call_sync(scenario: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    script = Script(scenario["responses"])
    monkeypatch.setattr(transport, "time", _Time(transport.time, script.sleep))
    client = Oblodai(
        public_id=PUBLIC_ID,
        secret=SECRET,
        http_client=httpx.Client(transport=httpx.MockTransport(script.handle)),
        env={},
    )
    result: Any = None
    error: Optional[BaseException] = None
    try:
        result = _bound(client, scenario["call"]["operation"])(*_args(scenario))
    except OblodaiError as err:
        error = err
    _check(scenario, script, result, error)


@pytest.mark.parametrize("scenario", _scenarios())
async def test_call_async(scenario: Dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    script = Script(scenario["responses"])
    monkeypatch.setattr(atransport, "asyncio", _Time(asyncio, script.asleep))
    client = AsyncOblodai(
        public_id=PUBLIC_ID,
        secret=SECRET,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(script.handle)),
        env={},
    )
    result: Any = None
    error: Optional[BaseException] = None
    try:
        result = await _bound(client, scenario["call"]["operation"])(*_args(scenario))
    except OblodaiError as err:
        error = err
    _check(scenario, script, result, error)
