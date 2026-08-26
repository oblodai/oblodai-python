"""What the SDK actually puts on the wire, and what its method docs promise about failures.

The fixtures in ``contract/`` are real requests the core answered 2xx to, so their key sets are
the vocabulary each route understands. A method that invents a field name sends something the
core silently ignores - and a method that names an error code the core cannot emit sends the
caller down a branch that never runs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import oblodai.resources
from oblodai import ERROR_CODES, ROUTES, Oblodai
from oblodai.core.pagination import Page
from tests.contract.test_routes import _declared_routes, _script
from tests.support.coverage import COVERAGE
from tests.support.fixtures import load_fixtures

# --- the docs may only name codes the core can actually emit ---------------------------------

_QUOTED_CODE = re.compile(r"``([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)``")
_RESOURCE_DIR = Path(oblodai.resources.__file__).parent


def _advertised_codes(text: str) -> List[str]:
    """Codes from the "Codes worth branching on" paragraphs, which is what callers `except` on."""
    codes: List[str] = []
    collecting = False
    for line in text.split("\n"):
        if "odes worth branching on" in line:
            collecting = True
        elif collecting and not line.strip():
            collecting = False
        if collecting:
            codes.extend(_QUOTED_CODE.findall(line))
    return codes


def test_every_error_code_named_in_a_method_doc_exists_in_the_catalogue() -> None:
    """A method that tells you to branch on a code the core never emits is worse than silence."""
    known = set(ERROR_CODES)
    advertised: List[str] = []
    unknown: List[str] = []
    for path in sorted(_RESOURCE_DIR.glob("*.py")):
        for code in _advertised_codes(path.read_text("utf-8")):
            advertised.append(code)
            if code not in known:
                unknown.append(f"{path.name}: {code}")
    assert not unknown, f"docstrings name codes the contract does not declare: {unknown}"
    # The money-moving methods must actually carry such a paragraph (C12 of the port brief).
    assert len(advertised) > 60, "the money-moving methods lost their error-code guidance"


# --- what the SDK puts on the wire, against the bodies the core actually accepted -------------


def _sent_body(key: str) -> Optional[Dict[str, Any]]:
    """Drive the coverage call once and hand back the JSON body it sent."""
    mock = _script(key)
    client = Oblodai(
        public_id="pk",
        secret="s",
        payout_public_id="wk",
        payout_secret="s2",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )
    result = COVERAGE[key](client)
    if isinstance(result, Page):
        result.first()
    body = mock.calls[0].json
    return body if isinstance(body, dict) else None


_WITH_RECORDED_BODY = sorted(
    key
    for key, spec in ROUTES.items()
    if spec.method == "POST" and load_fixtures().get(key, {}).get("request")
)


@pytest.mark.parametrize("key", _WITH_RECORDED_BODY)
def test_the_sdk_sends_only_fields_the_core_accepted(key: str) -> None:
    """A field name the SDK invents is a field the core silently ignores.

    The fixtures are real requests the core answered 2xx to, so their key sets are the vocabulary
    each route understands. A method that renames ``uuid`` to ``id`` fails here.
    """
    declared = _declared_routes()[key].get("request_schema") or {}
    accepted = set(load_fixtures()[key]["request"]) | set(declared.get("properties") or {})
    sent = _sent_body(key)
    if sent is None:
        pytest.skip(f"{key}: no JSON object body")
    unknown = set(sent) - accepted
    assert not unknown, (
        f"{key}: sends {sorted(unknown)}, which is neither in the core's own recorded request "
        "nor in its declared request schema"
    )
