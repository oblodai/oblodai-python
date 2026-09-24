"""The examples run: each ``examples/*.py`` executes against the same mock gateway as the README.

The scripts are what a merchant copies first, so a renamed method, a changed result shape or a
method that now returns a ``Job`` must break a test, not the merchant. Every ``httpx`` client the
SDK opens answers through ``test_readme_examples.answer`` (a minimal valid body per route); a few
answers are shaped so the script walks its main path instead of an early exit.
"""

from __future__ import annotations

import importlib.util
import io
import json
import time
from email.message import Message
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Dict, List

import httpx
import pytest

import oblodai.generated.models as models
from oblodai.core.signing import sign_webhook
from tests.support.samples import sample
from tests.unit.test_readme_examples import ROOT, _route_for, answer

EXAMPLES = ROOT / "examples"

#: operationId -> changes to the generic answer's ``result`` so the script takes its main path.
SHAPES: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "getPaymentInfo": lambda result: result.update(status="paid"),
    "validatePayout": lambda result: result.update(valid=True),
    "getBalance": lambda result: result["balance"].update(
        merchant=[sample(models.MerchantBalanceEntry, currency="USDT")]
    ),
}


def shaped(request: httpx.Request) -> httpx.Response:
    response = answer(request)
    op, route = _route_for(request.method, request.url.path)
    if route.bare or op not in SHAPES:
        return response
    body = json.loads(response.content)
    SHAPES[op](body["result"])
    return httpx.Response(200, content=json.dumps(body))


class _MockClient(httpx.Client):
    def __init__(self, **kw: Any) -> None:
        kw.setdefault("transport", httpx.MockTransport(shaped))
        super().__init__(**kw)


def load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"example_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", _MockClient)
    monkeypatch.setenv("OBLODAI_PUBLIC_ID", "example")
    monkeypatch.setenv("OBLODAI_SECRET", "s" * 32)
    monkeypatch.setenv("OBLODAI_WEBHOOK_SECRET", "whsec-example")


def test_every_example_is_covered() -> None:
    scripts = sorted(p.name for p in EXAMPLES.glob("*.py"))
    assert scripts == ["accept_payment.py", "payout.py", "sandbox.py", "webhook_receiver.py"]


#: example -> the line its main path ends on.
REACHES = {
    "accept_payment.py": "paid - release the goods",
    "payout.py": "payout ",
    "sandbox.py": "6. reset:",
}


@pytest.mark.parametrize("name", sorted(REACHES))
def test_example_main_runs(
    name: str, gateway: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load(EXAMPLES / name)
    if hasattr(module, "time"):  # polling examples: a clock that advances on sleep
        now: List[float] = [time.time()]
        monkeypatch.setattr(
            module,
            "time",
            SimpleNamespace(time=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s)),
        )
    module.main()
    out = capsys.readouterr().out
    assert REACHES[name] in out, f"{name} did not reach its main path:\n{out}"
    assert "refused" not in out


def _deliver(module: ModuleType, body: bytes, headers: Dict[str, str]) -> int:
    """POST one delivery to the example's handler; the HTTP status it answered."""
    handler = module.Handler.__new__(module.Handler)
    message = Message()
    for key, value in {**headers, "content-length": str(len(body))}.items():
        message[key] = value
    handler.headers = message
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.request_version = "HTTP/1.1"
    handler.requestline = "POST /oblodai/webhook HTTP/1.1"
    handler.command = "POST"
    handler.client_address = ("127.0.0.1", 0)
    handler.do_POST()
    return int(handler.wfile.getvalue().split(b" ", 2)[1])


def test_webhook_receiver_accepts_a_signed_delivery_and_rejects_a_forgery(
    gateway: None, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load(EXAMPLES / "webhook_receiver.py")
    event = {"type": "payment", "uuid": "u-1", "status": "paid", "sequence": 1}
    body = json.dumps(event).encode()
    ts = int(time.time())
    headers = {
        "X-Webhook-Timestamp": str(ts),
        "X-Webhook-Signature": sign_webhook("whsec-example", ts, body),
        "X-Webhook-Id": "d-1",
    }
    assert _deliver(module, body, headers) == 200
    assert "payment u-1 -> paid" in capsys.readouterr().out
    assert _deliver(module, body + b" ", headers) == 401
