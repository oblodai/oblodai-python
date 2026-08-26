"""Merchant onboarding: provisioned stores and the API key each is handed."""

from __future__ import annotations

from typing import Tuple, TypedDict


class ApiKeyPair(TypedDict):
    """The API key as minted by onboarding. The secret is shown once."""

    #: Public part of the key (sent as `X-Public-Id`).
    public_id: str
    #: Signing secret — shown only here, store it now.
    secret: str


class MerchantOnboarded(TypedDict):
    """`POST /v1/merchants` — a freshly provisioned merchant and its one API key."""

    merchant_id: str
    project_id: str
    #: The merchant's only key: it signs every route the SDK calls.
    api_key: ApiKeyPair


MERCHANT_ONBOARDED_KEYS: Tuple[str, ...] = (
    "merchant_id",
    "project_id",
    "api_key",
)


class SandboxStore(MerchantOnboarded):
    """`POST /v1/merchants/{id}/sandbox` — the merchant's dev store and its `test_` key."""

    #: False when the dev store already existed (the call is idempotent).
    created: bool


SANDBOX_STORE_KEYS: Tuple[str, ...] = (
    "merchant_id",
    "project_id",
    "api_key",
    "created",
)
