"""Route coverage: every operation of the contract has exactly one SDK method behind it.

The ledger (:mod:`tests.support.coverage`) is read off the generated namespaces. A method wired to
the wrong verb, path, gate or idempotency wrapper fails here, on both client tiers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Pattern

import pytest

from oblodai import ROUTES, Oblodai
from oblodai.aio import AsyncOblodai
from oblodai.core.errors import ContractError
from oblodai.core.pagination import AsyncPage, Page
from tests.support.coverage import COVERAGE, method_of, namespaces
from tests.support.coverage import call as call_operation
from tests.support.mock_http import MockHTTP, Scripted

ROUTE_KEYS: List[str] = sorted(ROUTES)

ANY_RESULT: Dict[str, Any] = {
    "state": 0,
    "result": {
        "items": [],
        "paginate": {"total": 0, "per_page": 1, "offset": 0, "has_pages": False},
        "enabled": True,
    },
}

_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def _path_pattern(path: str) -> Pattern[str]:
    """``/v1/pay/{id}/qr`` -> a regex whose ``{...}`` segments match one path segment each."""
    return re.compile(
        "^" + "[^/]+".join(re.escape(part) for part in _PLACEHOLDER.split(path)) + "$"
    )


def _script(key: str) -> MockHTTP:
    """A single scripted answer, shaped for the route's envelope (or lack of one)."""
    spec = ROUTES[key]
    answer = (
        Scripted(status=200, text="%PDF", headers={"content-type": "application/pdf"})
        if spec.bare
        else Scripted(status=200, body=ANY_RESULT)
    )
    return MockHTTP([answer])


def _assert_wire(mock: MockHTTP, key: str) -> None:
    """One request, on the declared verb and path, with the declared gate and idempotency wrapper.

    The gate is the whole credential story: a merchant has ONE API key, so every signed route
    carries it, a public route carries no signature at all, and the admin token appears on the
    onboarding routes and nowhere else - it is gateway-wide, and leaking it onto a merchant call
    would be worse than any 403.
    """
    spec = ROUTES[key]
    assert len(mock.calls) == 1, f"{key}: expected exactly one request, got {len(mock.calls)}"
    call = mock.calls[0]
    assert call.method == spec.method
    assert _path_pattern(spec.path).match(call.path), f"{key}: sent to {call.path}"
    if spec.auth == "public":
        assert "x-signature" not in call.headers, f"{key}: signed a public route"
        assert "x-admin-token" not in call.headers
    elif spec.auth == "onboard":
        assert "x-signature" not in call.headers
        assert call.headers["x-admin-token"] == "adm"
    else:
        assert spec.auth == "key", f"{key}: unknown gate {spec.auth!r}"
        assert call.headers["x-public-id"] == "pk", f"{key}: signed with something else"
        assert "x-admin-token" not in call.headers, f"{key}: leaked the admin token"
    if spec.idempotent:
        assert "idempotency-key" in call.headers, f"{key}: idempotent route sent no key"
    else:
        assert "idempotency-key" not in call.headers, f"{key}: sent a key the core would reject"


def _client(mock: MockHTTP) -> Oblodai:
    return Oblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )


def _async_client(mock: MockHTTP) -> AsyncOblodai:
    return AsyncOblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.async_client,
    )


@pytest.mark.parametrize("key", ROUTE_KEYS)
def test_sync_method_is_wired_to_the_route(key: str) -> None:
    mock = _script(key)
    try:
        result = call_operation(_client(mock), key)
        if isinstance(result, Page):
            result.first()  # list methods are lazy: nothing is sent until the page is consumed
    except (KeyError, TypeError, ValueError, ContractError):
        pass  # the placeholder answer does not parse into the model; the wire is what counts
    _assert_wire(mock, key)


@pytest.mark.parametrize("key", ROUTE_KEYS)
async def test_async_method_is_wired_to_the_route(key: str) -> None:
    mock = _script(key)
    # The async namespaces mirror the sync ones exactly; every method is a coroutine, and a list
    # method's coroutine gives a lazy ``AsyncPage`` whose ``__await__`` fetches the first page.
    try:
        result = await call_operation(_async_client(mock), key)
        if isinstance(result, AsyncPage):
            await result
    except (KeyError, TypeError, ValueError, ContractError):
        pass
    _assert_wire(mock, key)


def test_the_contract_only_ever_names_the_three_gates_this_sdk_implements() -> None:
    """`public` | `key` | `onboard`. A fourth would mean a credential the client cannot supply."""
    declared = {spec.auth for spec in ROUTES.values()}
    assert declared <= {"public", "key", "onboard"}, f"unknown gate in the contract: {declared}"


def test_routes_are_keyed_by_their_operation_id() -> None:
    for key, spec in ROUTES.items():
        assert spec.operation_id == key


def test_every_route_has_an_sdk_method_on_both_tiers() -> None:
    """The coverage ledger: every operation is reachable, and the async tier mirrors the sync."""
    assert set(COVERAGE) == set(ROUTES)
    for key in ROUTES:
        assert method_of(key, asynchronous=True) == method_of(key)


def test_the_client_exposes_every_namespace_of_the_contract() -> None:
    client = Oblodai(public_id="p", secret="s" * 32, env={})
    assert sorted(namespaces(client)) == sorted({ns for ns, _ in COVERAGE.values()})


def test_the_method_names_are_the_locked_public_names() -> None:
    """``names.lock`` is what the generator refuses to drop; the client must carry exactly it."""
    lock = Path(__file__).resolve().parents[2] / "names.lock"
    locked = [line for line in lock.read_text("utf-8").splitlines() if line.strip()]
    assert sorted(f"{ns}.{name}" for ns, name in COVERAGE.values()) == sorted(locked)


# --- paging ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", sorted(key for key, spec in ROUTES.items() if spec.list_kind == "paged")
)
def test_every_paged_route_asks_for_a_page(key: str) -> None:
    """A paged route with no way to ask for page two is one you can only read the top of."""
    mock = _script(key)
    result = call_operation(_client(mock), key)
    assert isinstance(result, Page), f"{key}: a paged route must return a lazy Page"
    result.first()
    call = mock.calls[0]
    sent: Any = call.json if call.method == "POST" else None
    limit = sent.get("limit") if isinstance(sent, dict) else call.query("limit")
    offset = sent.get("offset") if isinstance(sent, dict) else call.query("offset")
    assert limit is not None and offset is not None, f"{key}: no paging arguments on the wire"


def test_paging_arguments_reach_the_wire_in_either_spelling() -> None:
    """Both spellings - `list_history({"limit": 7})` and `list_history(limit=7)`."""
    for call_style in ("mapping", "keyword"):
        key = "listPayoutHistory"
        mock = _script(key)
        page = _client(mock).payouts.list_history
        if call_style == "mapping":
            page({"limit": 7, "offset": 14}).first()
        else:
            page(limit=7, offset=14).first()
        call = mock.calls[0]
        sent: Any = call.json if call.method == "POST" else None
        limit = str(sent["limit"]) if isinstance(sent, dict) else call.query("limit")
        offset = str(sent["offset"]) if isinstance(sent, dict) else call.query("offset")
        assert (limit, offset) == ("7", "14"), f"{key} ({call_style}): paging did not reach the wire"


def test_a_get_list_pages_through_the_query() -> None:
    mock = _script("sandboxListWebhooks")
    _client(mock).sandbox.list_webhooks().first()
    call = mock.calls[0]
    assert (call.query("limit"), call.query("offset")) == ("50", "0")


async def test_an_async_paged_route_returns_an_async_page() -> None:
    mock = _script("listPayoutHistory")
    page = await _async_client(mock).payouts.list_history(limit=3)
    assert isinstance(page, AsyncPage)
    assert not mock.calls, "a list is lazy: nothing is sent before the page is consumed"
    await page
    assert mock.calls[0].json["limit"] == 3
