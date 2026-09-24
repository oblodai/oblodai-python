"""``by_page()``: walk a list page by page, with exactly one request per page."""

from __future__ import annotations

from typing import List, Tuple

from oblodai.core.pagination import AsyncPage, Page, PageResult, Paginate

ITEMS = ["a", "b", "c", "d", "e", "f"]
PER_PAGE = 2


class Server:
    """Three pages of two items; records every ``(limit, offset)`` it is asked for."""

    def __init__(self) -> None:
        self.calls: List[Tuple[int, int]] = []

    def fetch(self, limit: int, offset: int) -> PageResult[str]:
        self.calls.append((limit, offset))
        chunk = ITEMS[offset : offset + limit]
        paginate: Paginate = {
            "total": len(ITEMS),
            "per_page": limit,
            "offset": offset,
            "has_pages": offset + limit < len(ITEMS),
        }
        return PageResult(chunk, paginate)

    async def afetch(self, limit: int, offset: int) -> PageResult[str]:
        return self.fetch(limit, offset)


def test_by_page_yields_every_page_with_one_request_each() -> None:
    server = Server()
    pages = list(Page(server.fetch, limit=PER_PAGE).by_page())
    assert len(pages) == 3
    assert all(isinstance(page, PageResult) for page in pages)
    assert [page.items for page in pages] == [["a", "b"], ["c", "d"], ["e", "f"]]
    assert server.calls == [(2, 0), (2, 2), (2, 4)]


def test_iterating_items_walks_the_same_three_requests() -> None:
    server = Server()
    assert list(Page(server.fetch, limit=PER_PAGE)) == ITEMS
    assert len(server.calls) == 3


def test_by_page_reuses_the_first_page_already_fetched() -> None:
    server = Server()
    page = Page(server.fetch, limit=PER_PAGE)
    page.first()
    assert len(list(page.by_page())) == 3
    assert len(server.calls) == 3


def test_by_page_starts_at_the_given_offset() -> None:
    server = Server()
    pages = list(Page(server.fetch, limit=PER_PAGE, offset=2).by_page())
    assert [page.offset for page in pages] == [2, 4]


async def test_async_by_page() -> None:
    server = Server()
    pages = [page async for page in AsyncPage(server.afetch, limit=PER_PAGE).by_page()]
    assert len(pages) == 3
    assert [page.items for page in pages] == [["a", "b"], ["c", "d"], ["e", "f"]]
    assert len(server.calls) == 3


async def test_async_iterating_items_makes_three_requests() -> None:
    server = Server()
    assert [item async for item in AsyncPage(server.afetch, limit=PER_PAGE)] == ITEMS
    assert len(server.calls) == 3
