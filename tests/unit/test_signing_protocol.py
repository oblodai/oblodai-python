"""The signing protocol has one source: ``x-oblodai-signing`` of the contract, generated into
``oblodai.generated.signing``. The runtime reads the header names, the canonical strings and the
limits from there, so a header the core renames reaches this SDK by regeneration alone."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict

import pytest

import oblodai.core.signing as core_signing
import oblodai.generated.signing as gen
from oblodai import webhooks
from oblodai.core import idempotency, request
from oblodai.core.signing import canonical_string, sign_request, sign_webhook
from tests.support.fixtures import load_signing

SRC = Path(__file__).resolve().parents[2] / "src" / "oblodai"

REQUEST_ROLES = ("public_id", "signature", "timestamp", "idempotency_key")
WEBHOOK_ROLES = (
    "timestamp",
    "signature",
    "signature_prev",
    "event",
    "id",
    "event_id",
    "event_time",
)


def _spec() -> Dict[str, Any]:
    signing = load_signing()
    if signing is None:
        pytest.skip("backend openapi.json not found (set OBLODAI_BACKEND)")
    return signing


def test_generated_constants_are_the_spec() -> None:
    spec = _spec()
    for role, name in zip(REQUEST_ROLES, spec["headers"], strict=True):
        assert getattr(gen, f"HEADER_{role.upper()}") == name
    for role, name in zip(WEBHOOK_ROLES, spec["webhook"]["headers"], strict=True):
        assert getattr(gen, f"HEADER_WEBHOOK_{role.upper()}") == name
    assert spec["skew_seconds"] == gen.SKEW_SECONDS
    assert spec["max_body"] == gen.MAX_BODY
    assert spec["max_idempotency_key_length"] == gen.MAX_IDEMPOTENCY_KEY_LENGTH
    assert spec["algorithm"] == gen.SIGNATURE_ALGORITHM


def test_public_names_alias_the_generated_values() -> None:
    for role in REQUEST_ROLES:
        name = f"HEADER_{role.upper()}"
        assert getattr(core_signing, name) is getattr(gen, name)
    for role in WEBHOOK_ROLES:
        name = f"HEADER_WEBHOOK_{role.upper()}"
        assert getattr(webhooks, name) is getattr(gen, name)
    assert core_signing.SIGNATURE_SKEW_SECONDS == gen.SKEW_SECONDS
    assert idempotency.MAX_IDEMPOTENCY_KEY_LENGTH == gen.MAX_IDEMPOTENCY_KEY_LENGTH
    assert {gen.HEADER_PUBLIC_ID.lower(), gen.HEADER_SIGNATURE.lower()} <= request.RESERVED_HEADERS


def test_webhook_window_defaults_to_the_contract_skew() -> None:
    for fn in (webhooks.verify, webhooks.verify_delivery):
        assert inspect.signature(fn).parameters["tolerance_sec"].default == gen.SKEW_SECONDS


def test_request_canonical_follows_the_generated_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_signing, "REQUEST_CANONICAL_ORDER", tuple(reversed(gen.REQUEST_CANONICAL_ORDER))
    )
    monkeypatch.setattr(core_signing, "REQUEST_CANONICAL_SEPARATOR", "|")
    assert canonical_string(7, "post", "/v1/x", "{}", "k") == "{}|k|/v1/x|POST|7"
    assert sign_request("s", 7, "post", "/v1/x", "{}", "k") == sign_request(
        "s", 7, "POST", "/v1/x", b"{}", "k"
    )


def test_webhook_canonical_follows_the_generated_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import hmac

    monkeypatch.setattr(core_signing, "WEBHOOK_CANONICAL_ORDER", ("payload", "ts"))
    monkeypatch.setattr(core_signing, "WEBHOOK_CANONICAL_SEPARATOR", "~")
    want = hmac.new(b"s", b"body~9", hashlib.sha256).hexdigest()
    assert sign_webhook("s", 9, "body") == want


def test_no_signing_header_is_spelled_outside_generated() -> None:
    """Every name of the spec's signing headers lives in ``generated/signing.py`` alone."""
    spec = _spec()
    names = [n.lower() for n in [*spec["headers"], *spec["webhook"]["headers"]]]
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path.parent.name == "generated":
            continue
        text = path.read_text("utf-8").lower()
        offenders += [f"{path.relative_to(SRC)}: {n}" for n in names if n in text]
    assert offenders == []
