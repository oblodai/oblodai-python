"""Merchant onboarding: provisioned stores and the key pairs they are handed."""

from __future__ import annotations

from typing import Tuple, TypedDict


class ApiKeyPair(TypedDict):
    """An API key pair as minted by onboarding. The secret is shown once."""

    #: Public part of the key (sent as the API key id).
    public_id: str
    #: Signing secret — shown only here, store it now.
    secret: str
    #: `api` — the unified key kind current merchants receive.
    kind: str


class MerchantOnboarded(TypedDict):
    """`POST /v1/merchants` — a freshly provisioned merchant and its keys."""

    merchant_id: str
    project_id: str
    #: The unified key (same as `payment_key`/`payout_key` for merchants created now).
    api_key: ApiKeyPair
    payment_key: ApiKeyPair
    payout_key: ApiKeyPair


MERCHANT_ONBOARDED_KEYS: Tuple[str, ...] = (
    "merchant_id",
    "project_id",
    "api_key",
    "payment_key",
    "payout_key",
)


class SandboxStore(MerchantOnboarded):
    """`POST /v1/merchants/{id}/sandbox` — the merchant's dev store and its `test_` key."""

    #: False when the dev store already existed (the call is idempotent).
    created: bool


SANDBOX_STORE_KEYS: Tuple[str, ...] = (
    "merchant_id",
    "project_id",
    "api_key",
    "payment_key",
    "payout_key",
    "created",
)
