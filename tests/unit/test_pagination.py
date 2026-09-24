"""Lazy pages: one page on demand, every page on iteration, nothing before that."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from oblodai import Oblodai, PaymentView, PayoutView, SandboxDelivery
from oblodai.aio import AsyncOblodai
from tests.support.mock_http import MockHTTP, Scripted
from tests.support.mock_http import page as raw_page
from tests.support.samples import sample

CREDS: Dict[str, Any] = {"public_id": "p", "secret": "s", "base_url": "https://api.test", "env": {}}


def item(number: int) -> Dict[str, Any]:
    """One list item that parses as a payment, a payout and a sandbox delivery alike."""
    uuid = str(number)
    return {
        **sample(PaymentView, uuid=uuid),
        **sample(PayoutView, uuid=uuid),
        **sample(SandboxDelivery, id=uuid),
    }


def page(numbers: List[int], offset: int, total: int, per_page: int) -> Scripted:
    return raw_page([item(n) for n in numbers], offset, total, per_page)


def items_of(listing: Any) -> List[int]:
    """The items' numbers, whatever model they parsed into."""
    return [int(getattr(entry, "uuid", None) or entry.id) for entry in listing]


def test_first_gives_one_page_and_iteration_walks_them_all() -> None:
    mock = MockHTTP(
        [
            page([1, 2], 0, 5, 2),
            page([1, 2], 0, 5, 2),
            page([3, 4], 2, 5, 2),
            page([5], 4, 5, 2),
        ]
    )
    api = Oblodai(http_client=mock.client, **CREDS)

    first = api.payments.list_history({"limit": 2}).first()
    assert items_of(first.items) == [1, 2]
    assert first.has_pages is True
    assert first.total == 5
    assert len(mock.calls) == 1

    seen: List[Any] = items_of(api.payments.list_history({"limit": 2}))
    assert seen == [1, 2, 3, 4, 5]
    assert len(mock.calls) == 4
    assert mock.calls[2].json == {"limit": 2, "offset": 2}


def test_attribute_access_fetches_the_first_page_once() -> None:
    mock = MockHTTP([page([1, 2], 0, 2, 2)])
    api = Oblodai(http_client=mock.client, **CREDS)
    listing = api.payouts.list_history({"limit": 2})
    assert items_of(listing.items) == [1, 2]
    assert listing.paginate["total"] == 2  # the server's block, as sent
    assert len(mock.calls) == 1


def test_all_collects_with_a_cap() -> None:
    mock = MockHTTP([page([1, 2], 0, 3, 2), page([3], 2, 3, 2)])
    api = Oblodai(http_client=mock.client, **CREDS)
    assert items_of(api.payouts.list_history({"limit": 2}).all()) == [1, 2, 3]

    capped = MockHTTP([page([1, 2], 0, 3, 2)])
    api = Oblodai(http_client=capped.client, **CREDS)
    assert items_of(api.payouts.list_history({"limit": 2}).all(max_items=2)) == [1, 2]
    assert len(capped.calls) == 1


def test_list_filters_travel_with_every_page() -> None:
    mock = MockHTTP([page([1], 0, 2, 1), page([2], 1, 2, 1)])
    api = Oblodai(http_client=mock.client, **CREDS)
    assert items_of(api.payouts.list_history({"limit": 1, "kind": "refund"})) == [1, 2]
    assert mock.calls[0].json == {"kind": "refund", "limit": 1, "offset": 0}
    assert mock.calls[1].json == {"kind": "refund", "limit": 1, "offset": 1}


def test_get_lists_travel_in_the_query_string() -> None:
    mock = MockHTTP([page([1, 2], 0, 2, 50)])
    api = Oblodai(http_client=mock.client, **CREDS)
    assert items_of(api.sandbox.list_webhooks()) == [1, 2]
    assert (mock.calls[0].query("limit"), mock.calls[0].query("offset")) == ("50", "0")
    assert mock.calls[0].body is None


def test_a_short_page_ends_the_walk() -> None:
    mock = MockHTTP([page([1, 2], 0, 99, 2), page([], 2, 99, 2)])
    api = Oblodai(http_client=mock.client, **CREDS)
    assert items_of(api.payments.list_history({"limit": 2})) == [1, 2]
    assert len(mock.calls) == 2


async def test_the_async_page_awaits_one_page_and_iterates_all() -> None:
    mock = MockHTTP(
        [
            page([1, 2], 0, 5, 2),
            page([1, 2], 0, 5, 2),
            page([3, 4], 2, 5, 2),
            page([5], 4, 5, 2),
        ]
    )
    api = AsyncOblodai(http_client=mock.async_client, **CREDS)
    listing = await api.payments.list_history({"limit": 2})
    first = await listing
    assert items_of(first.items) == [1, 2]
    assert len(mock.calls) == 1

    seen: List[Any] = []
    async for entry in await api.payments.list_history({"limit": 2}):
        seen.append(entry)
    assert items_of(seen) == [1, 2, 3, 4, 5]
    assert len(mock.calls) == 4
    await api.aclose()


async def test_the_async_page_requests_nothing_until_consumed() -> None:
    mock = MockHTTP([])
    api = AsyncOblodai(http_client=mock.async_client, **CREDS)
    await api.payments.list_history()
    assert mock.calls == []
    await api.aclose()


@pytest.mark.parametrize("limit", [1, 3])
async def test_async_all_collects_with_a_cap(limit: int) -> None:
    mock = MockHTTP([page([1, 2, 3], 0, 3, 3)])
    api = AsyncOblodai(http_client=mock.async_client, **CREDS)
    assert (
        items_of(await (await api.payouts.list_history({"limit": 3})).all(max_items=limit))
        == [1, 2, 3][:limit]
    )
    await api.aclose()
