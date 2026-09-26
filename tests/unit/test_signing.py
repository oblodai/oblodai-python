"""Signing: the vectors of the backend spec's ``x-oblodai-signing`` and the edge cases around them."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from oblodai.core.signing import canonical_string, sign_request, sign_webhook
from tests.support.fixtures import load_signing

SIGNING = load_signing()
SIGNING_VECTORS: List[Dict[str, Any]] = SIGNING["request_vectors"] if SIGNING else []
WEBHOOK_VECTORS: List[Dict[str, Any]] = SIGNING["webhook"]["vectors"] if SIGNING else []


def test_the_spec_has_signing_vectors() -> None:
    if SIGNING is None:
        pytest.skip("backend openapi.json not found (set OBLODAI_BACKEND)")
    assert SIGNING_VECTORS
    assert WEBHOOK_VECTORS


@pytest.mark.parametrize("vector", SIGNING_VECTORS, ids=[v["name"] for v in SIGNING_VECTORS])
def test_request_signature_matches_the_core(vector: Dict[str, Any]) -> None:
    key = vector["idempotency_key"] or None
    assert (
        canonical_string(vector["ts"], vector["method"], vector["request_uri"], vector["body"], key)
        == vector["canonical"]
    )
    assert (
        sign_request(
            vector["secret"],
            vector["ts"],
            vector["method"],
            vector["request_uri"],
            vector["body"],
            key,
        )
        == vector["signature"]
    )


def test_the_idempotency_slot_is_empty_not_absent() -> None:
    with_slot = sign_request("s", 1, "POST", "/v1/x", "{}")
    explicit_none = sign_request("s", 1, "POST", "/v1/x", "{}", None)
    assert with_slot == explicit_none
    assert canonical_string(1, "POST", "/v1/x", "{}") == "1\nPOST\n/v1/x\n\n{}"


def test_signs_the_body_bytes_so_text_and_bytes_agree() -> None:
    body = '{"additional_data":"tëst"}'
    assert sign_request("s", 5, "POST", "/v1/payment", body) == sign_request(
        "s", 5, "POST", "/v1/payment", body.encode("utf-8")
    )


def test_the_method_is_upper_cased_before_signing() -> None:
    assert sign_request("s", 1, "post", "/v1/x", "{}") == sign_request(
        "s", 1, "POST", "/v1/x", "{}"
    )


@pytest.mark.parametrize("index", range(len(WEBHOOK_VECTORS)))
def test_webhook_signature_matches_the_core(index: int) -> None:
    vector = WEBHOOK_VECTORS[index]
    assert sign_webhook(vector["secret"], vector["ts"], vector["payload"]) == vector["signature"]
