"""The public catalogues: supported assets and networks, and exchange rates."""

from __future__ import annotations

from typing import List, Tuple, TypedDict


class _CurrencyNetworkRequired(TypedDict):
    #: Blockchain network. Vocabulary: `Network`.
    network: str
    #: `native` (the chain's own coin) or `token` (a contract asset).
    kind: str
    #: Confirmations needed before a deposit is credited.
    min_confirmations: int
    #: Deposits and payouts both possible right now.
    available: bool
    #: Deposits possible right now.
    deposit_available: bool
    #: Payouts possible right now.
    payout_available: bool
    #: The network offered first on the pay page.
    default_offer: bool


class CurrencyNetwork(_CurrencyNetworkRequired, total=False):
    """One network an asset lives on, as `GET /v1/currencies` renders it."""

    #: Token contract address, for tokens.
    contract: str


CURRENCY_NETWORK_KEYS: Tuple[str, ...] = (
    "network",
    "kind",
    "min_confirmations",
    "available",
    "deposit_available",
    "payout_available",
    "default_offer",
)


class CurrencyInfo(TypedDict):
    """A payable asset and the networks it is available on."""

    currency: str
    #: Scale the amounts of this asset are rendered at.
    decimals: int
    networks: List[CurrencyNetwork]


class PricingCurrency(TypedDict):
    """A currency an invoice can be priced in (fiat or crypto)."""

    currency: str
    #: Scale the amounts of this currency are rendered at.
    decimals: int
    #: true — a fiat currency, not a coin.
    fiat: bool


class Currencies(TypedDict):
    """`GET /v1/currencies`."""

    #: Assets that can be paid and paid out.
    currencies: List[CurrencyInfo]
    #: Currencies an invoice can be priced in.
    pricing_currencies: List[PricingCurrency]


CURRENCIES_KEYS: Tuple[str, ...] = ("currencies", "pricing_currencies")

_ExchangeRateFields = TypedDict(
    "_ExchangeRateFields",
    {
        # Base currency of the quote.
        "from": str,
        # Quoted currency.
        "to": str,
        # How much `to` one unit of `from` buys, as a decimal string.
        "course": str,
    },
)


class ExchangeRate(_ExchangeRateFields):
    """`/v1/exchange-rate/list` item: 1 `from` = `course` `to` (`from` is a Python keyword — read
    it as ``rate["from"]``)."""


EXCHANGE_RATE_KEYS: Tuple[str, ...] = ("from", "to", "course")
