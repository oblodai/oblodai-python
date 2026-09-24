"""``_request`` serves every kind of generated method: paged lists and binary (``bare``) routes too.

Per Ruling 4 the calls go through test-local ``Resource`` subclasses with routes built here.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest

from oblodai import RawAPIResponse, RequestOptions, RouteSpec
from oblodai.aio.base import AsyncResource
from oblodai.core.errors import ConfigError
from oblodai.core.pagination import AsyncPage, Page, PageResult
from oblodai.resources.base import FileResult, Resource
from tests.support.clients import make_async_client, make_client

PAGED_POST = RouteSpec(
    method="POST",
    path="/v1/payout/history",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    list_kind="paged",
    operation_id="listPayouts",
)
PAGED_GET = RouteSpec(
    method="GET",
    path="/v1/sandbox/webhooks",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    list_kind="paged",
    operation_id="listSandboxWebhooks",
)
FILE = RouteSpec(
    method="GET",
    path="/v1/document/job/file",
    auth="key",
    idempotent=False,
    safe=True,
    bare=True,
    operation_id="downloadDocumentJobFile",
)

NO_OPTIONS = RequestOptions()
PDF = b"%PDF-1.7 fake"
ITEMS = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}, {"id": "e"}]


class Item:
    def __init__(self, raw: Dict[str, Any]) -> None:
        self.id = raw["id"]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> Item:
        return cls(raw)


class Things(Resource):
    def history(
        self, body: Optional[Dict[str, Any]] = None, options: RequestOptions = NO_OPTIONS
    ) -> Page[Item]:
        return self._request(PAGED_POST, body, options, parse=Item.from_dict)  # type: ignore[no-any-return]

    def hooks(self, query: Optional[Dict[str, Any]] = None) -> Page[Item]:
        return self._request(PAGED_GET, None, NO_OPTIONS, query=query, parse=Item.from_dict)  # type: ignore[no-any-return]

    def download(self, job_id: str) -> FileResult:
        return self._request(FILE, None, NO_OPTIONS, query={"job_id": job_id})  # type: ignore[no-any-return]


class AsyncThings(AsyncResource):
    async def history(self, body: Optional[Dict[str, Any]] = None) -> AsyncPage[Item]:
        return await self._request(PAGED_POST, body, NO_OPTIONS, parse=Item.from_dict)  # type: ignore[no-any-return]

    async def download(self, job_id: str) -> FileResult:
        return await self._request(FILE, None, NO_OPTIONS, query={"job_id": job_id})  # type: ignore[no-any-return]


class Server:
    """Answers paged routes from ITEMS by limit/offset (body for POST, query for GET), the file
    route with PDF bytes; records every request."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []

    def params(self, request: httpx.Request) -> Dict[str, Any]:
        if request.method == "GET":
            return dict(request.url.params)
        return json.loads(request.content or b"{}")  # type: ignore[no-any-return]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == FILE.path:
            return httpx.Response(
                200,
                content=PDF,
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="report.pdf"',
                },
            )
        params = self.params(request)
        limit, offset = int(params["limit"]), int(params["offset"])
        chunk = ITEMS[offset : offset + limit]
        paginate = {
            "total": len(ITEMS),
            "per_page": limit,
            "offset": offset,
            "has_pages": offset + limit < len(ITEMS),
        }
        return httpx.Response(
            200, json={"state": 0, "result": {"items": chunk, "paginate": paginate}}
        )


# --- paged ---------------------------------------------------------------------------------------


def test_paged_route_returns_a_lazy_page_of_parsed_items() -> None:
    server = Server()
    things = Things(make_client(server).transport)
    page = things.history({"limit": 2, "status": "done"})
    assert isinstance(page, Page)
    assert server.requests == []  # lazy
    pages = list(page.by_page())
    assert [[i.id for i in p.items] for p in pages] == [["a", "b"], ["c", "d"], ["e"]]
    assert all(isinstance(i, Item) for p in pages for i in p.items)
    bodies = [json.loads(r.content) for r in server.requests]
    assert bodies == [
        {"status": "done", "limit": 2, "offset": 0},
        {"status": "done", "limit": 2, "offset": 2},
        {"status": "done", "limit": 2, "offset": 4},
    ]


def test_paged_get_route_pages_through_the_query() -> None:
    server = Server()
    things = Things(make_client(server).transport)
    assert [i.id for i in things.hooks({"limit": 3, "offset": 1})] == ["b", "c", "d", "e"]
    assert [dict(r.url.params) for r in server.requests] == [
        {"limit": "3", "offset": "1"},
        {"limit": "3", "offset": "4"},
    ]
    assert all(r.content == b"" for r in server.requests)


def test_paged_route_rejects_an_idempotency_key_it_cannot_honour() -> None:
    things = Things(make_client(Server()).transport)
    with pytest.raises(ConfigError):
        things.history(None, RequestOptions(idempotency_key="k"))


def test_raw_paged_route_fetches_the_first_page_and_parses_into_a_page() -> None:
    server = Server()
    things = Things(make_client(server).transport)
    raw = things.with_raw_response.history({"limit": 2})
    assert isinstance(raw, RawAPIResponse)
    assert raw.status == 200
    assert len(server.requests) == 1
    page = raw.parse()
    assert isinstance(page, Page)
    assert [i.id for i in page.first().items] == ["a", "b"]
    assert len(server.requests) == 1  # the first page is the raw response itself
    assert [i.id for i in page] == ["a", "b", "c", "d", "e"]
    assert len(server.requests) == 3


async def test_async_paged_route_returns_an_async_page() -> None:
    server = Server()
    things = AsyncThings(make_async_client(server).transport)
    page = await things.history({"limit": 2})
    assert isinstance(page, AsyncPage)
    ids = [p.items async for p in page.by_page()]
    assert [[i.id for i in chunk] for chunk in ids] == [["a", "b"], ["c", "d"], ["e"]]


async def test_async_raw_paged_route() -> None:
    server = Server()
    things = AsyncThings(make_async_client(server).transport)
    raw = await things.with_raw_response.history({"limit": 4})
    page = raw.parse()
    assert isinstance(page, AsyncPage)
    first = await page.first()
    assert isinstance(first, PageResult)
    assert [i.id for i in first.items] == ["a", "b", "c", "d"]
    assert [i.id for i in await page.all()] == ["a", "b", "c", "d", "e"]
    assert len(server.requests) == 2


# --- bare ----------------------------------------------------------------------------------------


def test_bare_route_returns_the_file() -> None:
    server = Server()
    result = Things(make_client(server).transport).download("j1")
    assert isinstance(result, FileResult)
    assert result.content == PDF
    assert result.content_type == "application/pdf"
    assert result.filename == "report.pdf"
    assert dict(server.requests[0].url.params) == {"job_id": "j1"}


def test_raw_bare_route_parses_into_the_file() -> None:
    raw = Things(make_client(Server()).transport).with_raw_response.download("j1")
    assert isinstance(raw, RawAPIResponse)
    assert raw.content == PDF
    parsed = raw.parse()
    assert isinstance(parsed, FileResult)
    assert parsed.filename == "report.pdf"


async def test_async_bare_route_and_raw() -> None:
    things = AsyncThings(make_async_client(Server()).transport)
    result = await things.download("j1")
    assert isinstance(result, FileResult) and result.content == PDF
    raw = await things.with_raw_response.download("j1")
    assert raw.parse().content == PDF
