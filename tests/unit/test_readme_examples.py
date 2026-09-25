"""The README code runs: every ```python block of both READMEs executes against a mock gateway.

Blocks of one README run in order in one namespace, the way a reader pastes them one after another
(the quick start makes ``oblodai``, later blocks use it). Every ``httpx`` client the SDK opens is
backed by ``httpx.MockTransport``: any route of ``ROUTES`` answers with a minimal valid body for the
model its generated method parses, so a renamed method, argument or field breaks this test.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import time
import typing
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

import oblodai
import oblodai.generated.models as models
import oblodai.generated.resources as generated
from oblodai.core.signing import sign_webhook
from oblodai.generated.routes import ROUTES
from oblodai.generated.signing import HEADER_WEBHOOK_SIGNATURE, HEADER_WEBHOOK_TIMESTAMP
from tests.support.samples import sample

ROOT = Path(oblodai.__file__).resolve().parents[2]
READMES = ("README.md", "README.ru.md")
_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def blocks(document: str) -> List[str]:
    return [m.group(1) for m in _BLOCK.finditer((ROOT / document).read_text("utf-8"))]


def _parsers() -> Dict[str, Optional[str]]:
    """``operationId`` -> the model name its generated method parses the result with."""
    out: Dict[str, Optional[str]] = {}
    for node in ast.walk(ast.parse(inspect.getsource(generated))):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        first = node.args[0]
        if not (
            isinstance(first, ast.Subscript)
            and isinstance(first.value, ast.Name)
            and first.value.id == "ROUTES"
            and isinstance(first.slice, ast.Constant)
        ):
            continue
        parse = next((kw.value for kw in node.keywords if kw.arg == "parse"), None)
        name = None
        if isinstance(parse, ast.Attribute) and isinstance(parse.value, ast.Name):
            name = parse.value.id
        out[str(first.slice.value)] = name
    return out


PARSERS = _parsers()


def _route_for(method: str, path: str) -> Tuple[str, Any]:
    for op, route in ROUTES.items():
        pattern = "^" + re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(route.path)) + "$"
        if route.method == method and re.match(pattern, path):
            return op, route
    raise AssertionError(f"README calls a route the API does not have: {method} {path}")


def answer(request: httpx.Request) -> httpx.Response:
    """A minimal valid answer for whatever route the README called."""
    op, route = _route_for(request.method, request.url.path)
    if route.bare:
        return httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
    name = PARSERS.get(op)
    if name is None:
        raise AssertionError(f"README example calls {op}: teach this test its result shape")
    model = getattr(models, name)
    if route.list_kind is not None:
        result: Any = {"items": [sample(model)]}
        if route.list_kind == "paged":
            result["paginate"] = {"total": 1, "per_page": 50, "offset": 0, "has_pages": False}
    else:
        result = sample(model)
    return httpx.Response(200, content=json.dumps({"state": 0, "result": result}))


class _MockClient(httpx.Client):
    def __init__(self, **kw: Any) -> None:
        kw.setdefault("transport", httpx.MockTransport(answer))
        super().__init__(**kw)


class _MockAsyncClient(httpx.AsyncClient):
    def __init__(self, **kw: Any) -> None:
        kw.setdefault("transport", httpx.MockTransport(answer))
        super().__init__(**kw)


def test_readmes_have_blocks_and_share_the_code() -> None:
    en, ru = blocks("README.md"), blocks("README.ru.md")
    assert len(en) >= 8
    assert en == ru, "the Russian README must carry the same code blocks as the English one"


def test_the_block_extractor_sees_the_quick_start() -> None:
    assert any("oblodai.payments.create(" in block for block in blocks("README.md"))
    assert typing.get_type_hints(models.PaymentView)  # the sampler has a model to work with


@pytest.mark.parametrize("document", READMES)
def test_readme_blocks_run(document: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", _MockClient)
    monkeypatch.setattr(httpx, "AsyncClient", _MockAsyncClient)
    monkeypatch.setenv("OBLODAI_PUBLIC_ID", "readme")
    monkeypatch.setenv("OBLODAI_SECRET", "s" * 32)
    namespace: Dict[str, Any] = {"__name__": "readme"}
    for index, source in enumerate(blocks(document)):
        try:
            exec(compile(source, f"{document}#{index}", "exec"), namespace)
        except Exception as err:  # pragma: no cover - the message is the point
            pytest.fail(f"{document} block #{index} fails: {type(err).__name__}: {err}\n{source}")

    # The webhook block defines a receiver; drive it with one signed delivery and one forgery.
    receive = namespace["receive"]
    namespace["endpoint_secret"] = secret = "whsec-readme"  # the mock registration returned none
    body = json.dumps({"type": "payment", "uuid": "u", "status": "paid"}).encode()
    ts = int(time.time())
    headers = {
        HEADER_WEBHOOK_TIMESTAMP: str(ts),
        HEADER_WEBHOOK_SIGNATURE: sign_webhook(secret, ts, body),
    }
    assert receive(body, headers, None) == 200
    assert receive(body + b" ", headers, None) == 401
