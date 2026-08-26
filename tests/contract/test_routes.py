"""Route coverage: every route the core declares has exactly one SDK method behind it.

The table below is the SDK's coverage ledger. A new core route fails this suite until a method is
wired to it, and a method wired to the wrong verb, path, gate or idempotency wrapper fails too.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Pattern, cast

import pytest

import oblodai.aio.resources
import oblodai.resources
from oblodai import ROUTES, Oblodai
from oblodai.aio import AsyncOblodai
from oblodai.core.pagination import Page
from tests.support.coverage import COVERAGE
from tests.support.fixtures import load_contract, load_fixtures
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


@pytest.mark.parametrize("key", ROUTE_KEYS)
def test_sync_method_is_wired_to_the_route(key: str) -> None:
    mock = _script(key)
    client = Oblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )
    result = COVERAGE[key](client)
    if isinstance(result, Page):
        result.first()  # list methods are lazy: nothing is sent until the page is consumed
    _assert_wire(mock, key)


@pytest.mark.parametrize("key", ROUTE_KEYS)
async def test_async_method_is_wired_to_the_route(key: str) -> None:
    mock = _script(key)
    client = AsyncOblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.async_client,
    )
    # The async namespaces mirror the sync ones exactly; only the return values are awaitable
    # (a coroutine, or an ``AsyncPage`` whose ``__await__`` fetches the first page).
    result = COVERAGE[key](cast(Oblodai, client))
    await result
    _assert_wire(mock, key)


_SKIP_PATH = re.compile(r"^/(healthz|readyz|docs|openapi\.json|internal)")


def _declared_routes() -> Dict[str, Dict[str, Any]]:
    """The merchant-facing rows of ``contract.json``, keyed the way ``ROUTES`` is."""
    return {
        f"{route['method']} {route['path']}": route
        for route in load_contract()["routes"]
        if not _SKIP_PATH.match(route["path"])
    }


def test_routes_are_the_cores_merchant_surface() -> None:
    """Nothing more and nothing less than what ``contract.json`` declares."""
    assert set(ROUTES) == set(_declared_routes())


#: Every field of a RouteSpec, and the name ``contract.json`` gives it.
ROUTE_FIELDS = (
    ("method", "method"),
    ("path", "path"),
    ("auth", "auth"),
    ("idempotent", "idempotent"),
    ("safe", "safe"),
    ("bare", "bare"),
    ("list_kind", "list"),
)


def route_field(route: Dict[str, Any], name: str) -> Any:
    """``contract.json`` omits a false ``bare`` and a routes' missing ``list``."""
    value = route.get(name)
    if name in ("idempotent", "safe", "bare"):
        return bool(value)
    return value or None if name == "list" else value


@pytest.mark.parametrize("key", ROUTE_KEYS)
def test_route_spec_matches_the_contract_field_for_field(key: str) -> None:
    """Not just the key set: every flag the SDK acts on comes from the core, verbatim.

    ``safe`` in particular decides whether a request may be re-sent after a transport failure -
    a flipped bit here is a duplicate payout, so it is compared, not assumed.
    """
    declared = _declared_routes()[key]
    spec = ROUTES[key]
    for attribute, field in ROUTE_FIELDS:
        assert getattr(spec, attribute) == route_field(declared, field), (
            f"{key}: {attribute}={getattr(spec, attribute)!r} but the contract says "
            f"{field}={route_field(declared, field)!r}"
        )


def test_the_field_comparison_catches_a_flipped_flag() -> None:
    """The mutation test for the check above: flip one bit, the comparison must notice."""
    key = "POST /v1/payout"
    declared = dict(_declared_routes()[key])
    assert declared["safe"] is False
    declared["safe"] = True
    assert ROUTES[key].safe != route_field(declared, "safe")
    declared = dict(_declared_routes()[key])
    declared["auth"] = "public"
    assert ROUTES[key].auth != route_field(declared, "auth")


def test_the_contract_only_ever_names_the_three_gates_this_sdk_implements() -> None:
    """`public` | `key` | `onboard`. A fourth would mean a credential the client cannot supply."""
    declared = {route["auth"] for route in _declared_routes().values()}
    assert declared <= {"public", "key", "onboard"}, f"unknown gate in the contract: {declared}"
    assert {spec.auth for spec in ROUTES.values()} == declared


def test_every_recorded_fixture_belongs_to_a_known_route() -> None:
    for route in load_fixtures():
        assert route in ROUTES, f"{route}: fixture for a route the SDK does not know"


def test_every_route_has_an_sdk_method() -> None:
    """The coverage ledger: a new core route fails here until a method is wired to it."""
    assert set(COVERAGE) == set(ROUTES)


# --- paging and aliases (C11 of the port brief) -----------------------------------------------

ALIASES = (
    ("payments", "get", "info"),
    ("payments", "list", "history"),
    ("payouts", "get", "info"),
    ("payouts", "list", "history"),
    ("payout_links", "get", "info"),
    ("payment_links", "get", "info"),
)


def _client(mock: MockHTTP) -> Oblodai:
    return Oblodai(
        public_id="pk",
        secret="s",
        admin_token="adm",
        base_url="https://api.test",
        http_client=mock.client,
    )


@pytest.mark.parametrize(("namespace", "alias", "canonical"), ALIASES)
def test_an_alias_has_the_same_signature_as_the_method_it_aliases(
    namespace: str, alias: str, canonical: str
) -> None:
    """`get` must be callable exactly like `info`, on both tiers, or it is not an alias."""
    sync_client = _client(MockHTTP([]))
    async_client = AsyncOblodai(base_url="https://api.test", env={})
    try:
        for tier in (sync_client, async_client):
            target = type(getattr(tier, namespace))
            assert inspect.signature(getattr(target, alias)) == inspect.signature(
                getattr(target, canonical)
            ), f"{target.__name__}.{alias} does not match .{canonical}"
    finally:
        sync_client.close()


@pytest.mark.parametrize(
    "key", sorted(key for key, spec in ROUTES.items() if spec.list_kind == "paged")
)
def test_every_paged_route_asks_for_a_page(key: str) -> None:
    """A paged route with no way to ask for page two is one you can only read the top of."""
    mock = _script(key)
    result = COVERAGE[key](_client(mock))
    assert isinstance(result, Page), f"{key}: a paged route must return a lazy Page"
    result.first()
    call = mock.calls[0]
    sent: Any = call.json if call.method == "POST" else None
    limit = sent.get("limit") if isinstance(sent, dict) else call.query("limit")
    offset = sent.get("offset") if isinstance(sent, dict) else call.query("offset")
    assert limit is not None and offset is not None, f"{key}: no paging arguments on the wire"


@pytest.mark.parametrize("key", ["POST /v1/payout/history", "GET /v1/sandbox/webhooks"])
def test_paging_arguments_reach_the_wire_as_a_body_or_as_a_query(key: str) -> None:
    """Both spellings - `history({"limit": 7})` and `history(limit=7)` - and both transports."""
    for call_style in ("mapping", "keyword"):
        mock = _script(key)
        client = _client(mock)
        page = (
            client.payouts.history
            if key == "POST /v1/payout/history"
            else client.sandbox.webhooks
        )
        if call_style == "mapping":
            page({"limit": 7, "offset": 14}).first()
        else:
            page(limit=7, offset=14).first()
        call = mock.calls[0]
        sent: Any = call.json if call.method == "POST" else None
        limit = str(sent["limit"]) if isinstance(sent, dict) else call.query("limit")
        offset = str(sent["offset"]) if isinstance(sent, dict) else call.query("offset")
        assert (limit, offset) == ("7", "14"), f"{key} ({call_style}): paging did not reach the wire"
