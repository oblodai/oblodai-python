"""What the SDK actually puts on the wire, and what its method docs promise about failures.

The fixtures in ``contract/`` are real requests the core answered 2xx to, so their key sets are
the vocabulary each route understands. Every one of them must be expressible through the method's
keyword arguments and reach the wire unchanged - and a method doc that names an error code the
core cannot emit sends the caller down a branch that never runs.
"""

from __future__ import annotations

import inspect
import keyword
import re
from typing import Any, Dict, List

import pytest

import oblodai.generated.resources as generated
from oblodai import ROUTES, ErrorCode, Oblodai
from oblodai.core.pagination import Page
from tests.contract.test_routes import _script
from tests.support.coverage import PATH_VALUE, method_of
from tests.support.fixtures import load_fixtures

BY_KEY = {spec.key: op for op, spec in ROUTES.items()}

# --- the docs may only name codes the core can actually emit ---------------------------------

_RAISES = re.compile(r"Raises: (.*?)(?:\n\s*\n|\"\"\")", re.S)


def test_every_error_code_named_in_a_method_doc_exists_in_the_catalogue() -> None:
    """A method that tells you to branch on a code the core never emits is worse than silence."""
    known = {code.value for code in ErrorCode}
    advertised: List[str] = []
    for block in _RAISES.findall(inspect.getsource(generated)):
        advertised.extend(code.strip() for code in block.replace("\n", " ").split(","))
    unknown = sorted({code for code in advertised if code and code not in known})
    assert not unknown, f"docstrings name codes the contract does not declare: {unknown}"
    assert len(advertised) > 500, "the methods lost their error-code guidance"


# --- what the SDK puts on the wire, against the bodies the core actually accepted -------------


_WITH_RECORDED_BODY = sorted(
    key
    for key, fixture in load_fixtures().items()
    if key in BY_KEY
    and ROUTES[BY_KEY[key]].method == "POST"
    and isinstance(fixture.get("request"), dict)
    and fixture["request"]
)


def _client(key: str) -> Any:
    mock = _script(BY_KEY[key])
    client = Oblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )
    namespace, name = method_of(BY_KEY[key])
    return mock, getattr(getattr(client, namespace), name)


def _send(key: str, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    mock, method = _client(key)
    positional = [
        p
        for p in inspect.signature(method).parameters.values()
        if p.kind is inspect.Parameter.POSITIONAL_ONLY and p.name != "params"
    ]
    try:
        result = method(*[PATH_VALUE] * len(positional), *args, **kwargs)
        if isinstance(result, Page):
            result.first()
    except Exception:
        pass  # the placeholder answer need not parse; the request is what is checked
    body = mock.calls[0].json
    assert isinstance(body, dict)
    return body


def py_name(wire: str) -> str:
    """The keyword a wire field is spelled as: a Python keyword gets a trailing underscore."""
    return wire + "_" if keyword.iskeyword(wire) else wire


@pytest.mark.parametrize("key", _WITH_RECORDED_BODY)
def test_a_recorded_request_reaches_the_wire_through_keyword_arguments(key: str) -> None:
    """Every field of a request the core accepted is a keyword of the method, sent verbatim.

    A method that renames ``uuid`` to ``id`` - or lacks a field the core reads - fails here.
    """
    recorded: Dict[str, Any] = load_fixtures()[key]["request"]
    _, method = _client(key)
    keywords = {
        p.name
        for p in inspect.signature(method).parameters.values()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    }
    as_arguments = {py_name(name): value for name, value in recorded.items()}
    missing = sorted(set(as_arguments) - keywords)
    assert not missing, f"{key}: no keyword argument for {missing}"
    sent = _send(key, **as_arguments)
    limitless = {k: v for k, v in sent.items() if k not in ("limit", "offset")}
    assert limitless == {k: v for k, v in recorded.items() if k not in ("limit", "offset")}


@pytest.mark.parametrize("key", _WITH_RECORDED_BODY)
def test_a_recorded_request_passes_through_params_unchanged(key: str) -> None:
    recorded: Dict[str, Any] = load_fixtures()[key]["request"]
    sent = _send(key, recorded)
    limitless = {k: v for k, v in sent.items() if k not in ("limit", "offset")}
    assert limitless == {k: v for k, v in recorded.items() if k not in ("limit", "offset")}
