"""Offset pagination over the core's ``{items, paginate}`` lists.

``paginate.has_pages`` is the server's own "there is more" flag; iteration stops on it, or on a
short page, whichever comes first. A list method returns a lazy :class:`Page` (or
:class:`AsyncPage`): nothing is requested until it is consumed, and the first page is fetched once
however many ways it is consumed.
"""

from __future__ import annotations

from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Generic,
    Iterator,
    List,
    Optional,
    TypeVar,
)

from ..contract.models.common import Paginate

__all__ = ["DEFAULT_PAGE_LIMIT", "AsyncPage", "Page", "PageResult"]

T = TypeVar("T")

DEFAULT_PAGE_LIMIT = 50

#: ``(limit, offset) -> one page``
PageFetcher = Callable[[int, int], "PageResult[T]"]
AsyncPageFetcher = Callable[[int, int], Awaitable["PageResult[T]"]]


class PageResult(Generic[T]):
    """One page of a list: its items plus the server's pagination block."""

    __slots__ = ("items", "paginate")

    def __init__(self, items: List[T], paginate: Paginate) -> None:
        self.items = items
        self.paginate = paginate

    @property
    def total(self) -> int:
        return int(self.paginate.get("total", 0))

    @property
    def per_page(self) -> int:
        return int(self.paginate.get("per_page", len(self.items)))

    @property
    def offset(self) -> int:
        return int(self.paginate.get("offset", 0))

    @property
    def has_pages(self) -> bool:
        return bool(self.paginate.get("has_pages", False))

    def __iter__(self) -> Iterator[T]:
        """Iterate THIS page's items only (use the :class:`Page` object to walk every page)."""
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __repr__(self) -> str:
        return (
            f"PageResult(items={len(self.items)}, total={self.total}, has_pages={self.has_pages})"
        )


class Page(Generic[T]):
    """A lazy list handle.

    ``for item in page`` walks every item across every page, ``page.by_page()`` every page;
    ``page.first()`` (or ``page.items`` / ``page.paginate``) gives just the first page. Nothing is fetched until one of those happens.
    """

    __slots__ = ("_fetch", "_first", "_limit", "_offset")

    def __init__(
        self,
        fetch: PageFetcher[T],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        *,
        first: Optional[PageResult[T]] = None,
    ) -> None:
        """``first`` is the first page when it is already at hand (a raw response's)."""
        self._fetch = fetch
        self._limit = DEFAULT_PAGE_LIMIT if limit is None else limit
        self._offset = 0 if offset is None else offset
        self._first: Optional[PageResult[T]] = first

    def first(self) -> PageResult[T]:
        """The first page, fetched once and cached."""
        if self._first is None:
            self._first = self._fetch(self._limit, self._offset)
        return self._first

    @property
    def items(self) -> List[T]:
        """Items of the first page."""
        return self.first().items

    @property
    def paginate(self) -> Paginate:
        """Pagination block of the first page."""
        return self.first().paginate

    def by_page(self) -> Iterator[PageResult[T]]:
        """Every page in turn, one request each (the first page is reused when already fetched)."""
        offset = self._offset
        page = self.first()
        while True:
            yield page
            got = len(page.items)
            offset += got
            if got == 0 or not page.has_pages:
                return
            page = self._fetch(self._limit, offset)

    def __iter__(self) -> Iterator[T]:
        for page in self.by_page():
            yield from page.items

    def all(self, max_items: Optional[int] = None) -> List[T]:
        """Collect every item into a list (bounded by ``max_items`` when given)."""
        out: List[T] = []
        if max_items is not None and max_items <= 0:
            return out
        for item in self:
            out.append(item)
            # Stop before the iterator resumes, so a cap never costs an extra page request.
            if max_items is not None and len(out) >= max_items:
                break
        return out

    def __repr__(self) -> str:
        state = "fetched" if self._first is not None else "not fetched"
        return f"Page(limit={self._limit}, offset={self._offset}, {state})"


class AsyncPage(Generic[T]):
    """The async twin of :class:`Page`: ``await page`` for one page, ``async for`` for all items,
    ``async for page in page.by_page()`` for every page."""

    __slots__ = ("_fetch", "_first", "_limit", "_offset")

    def __init__(
        self,
        fetch: AsyncPageFetcher[T],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        *,
        first: Optional[PageResult[T]] = None,
    ) -> None:
        """``first`` is the first page when it is already at hand (a raw response's)."""
        self._fetch = fetch
        self._limit = DEFAULT_PAGE_LIMIT if limit is None else limit
        self._offset = 0 if offset is None else offset
        self._first: Optional[PageResult[T]] = first

    async def first(self) -> PageResult[T]:
        """The first page, fetched once and cached."""
        if self._first is None:
            self._first = await self._fetch(self._limit, self._offset)
        return self._first

    def __await__(self) -> Generator[Any, None, PageResult[T]]:
        return self.first().__await__()

    async def by_page(self) -> AsyncIterator[PageResult[T]]:
        """Every page in turn, one request each (the first page is reused when already fetched)."""
        offset = self._offset
        page = await self.first()
        while True:
            yield page
            got = len(page.items)
            offset += got
            if got == 0 or not page.has_pages:
                return
            page = await self._fetch(self._limit, offset)

    async def __aiter__(self) -> AsyncIterator[T]:
        async for page in self.by_page():
            for item in page.items:
                yield item

    async def all(self, max_items: Optional[int] = None) -> List[T]:
        """Collect every item into a list (bounded by ``max_items`` when given)."""
        out: List[T] = []
        if max_items is not None and max_items <= 0:
            return out
        async for item in self:
            out.append(item)
            # Stop before the iterator resumes, so a cap never costs an extra page request.
            if max_items is not None and len(out) >= max_items:
                break
        return out

    def __repr__(self) -> str:
        state = "fetched" if self._first is not None else "not fetched"
        return f"AsyncPage(limit={self._limit}, offset={self._offset}, {state})"
