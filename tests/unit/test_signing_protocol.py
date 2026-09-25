"""The signing protocol has one source: ``x-oblodai-signing`` of the contract, generated into
``oblodai.generated.signing``. The runtime reads the header names, the canonical strings and the
limits from there, so a header the core renames reaches this SDK by regeneration alone."""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any, Dict, List, Pattern

import pytest

import oblodai.core.signing as core_signing
import oblodai.generated.signing as gen
from oblodai import webhooks
from oblodai.core import idempotency, request
from oblodai.core.signing import canonical_string, sign_request, sign_webhook
from tests.support.fixtures import load_signing

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "oblodai"


def _hand_written() -> List[Path]:
    """Every hand-written Python file that ships: the library outside ``generated/`` and the
    examples (they go into the sdist and the README tests run them)."""
    files = [p for p in SRC.rglob("*.py") if p.parent.name != "generated"]
    files += (ROOT / "examples").rglob("*.py")
    assert any(p.is_relative_to(ROOT / "examples") for p in files), "no examples scanned"
    return sorted(files)


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
    assert spec["webhook"]["test_header"] == gen.HEADER_WEBHOOK_TEST
    assert spec["skew_seconds"] == gen.SKEW_SECONDS
    assert spec["max_body"] == gen.MAX_BODY
    assert spec["max_idempotency_key_length"] == gen.MAX_IDEMPOTENCY_KEY_LENGTH
    assert spec["algorithm"] == gen.SIGNATURE_ALGORITHM


def test_public_names_alias_the_generated_values() -> None:
    for role in REQUEST_ROLES:
        name = f"HEADER_{role.upper()}"
        assert getattr(core_signing, name) is getattr(gen, name)
    for role in (*WEBHOOK_ROLES, "test"):
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
    """Every name of the spec's signing headers lives in ``generated/signing.py`` alone - neither the
    library nor the examples spell one."""
    spec = _spec()
    webhook = spec["webhook"]
    names = [n.lower() for n in [*spec["headers"], *webhook["headers"], webhook["test_header"]]]
    offenders = []
    for path in _hand_written():
        text = path.read_text("utf-8").lower()
        offenders += [f"{path.relative_to(ROOT)}: {n}" for n in names if n in text]
    assert offenders == []


def _limit_patterns() -> List[Pattern[str]]:
    """The body and idempotency-key limits as source literals: decimal, and ``1 << n`` for a power of
    two. The skew is not scanned for — its value is also an HTTP status class (``< 300``); the alias
    assertions above hold it."""
    pats = [
        re.compile(rf"(?<![\w.]){limit}(?![\w.])")
        for limit in (gen.MAX_BODY, gen.MAX_IDEMPOTENCY_KEY_LENGTH)
    ]
    if gen.MAX_BODY & (gen.MAX_BODY - 1) == 0:
        pats.append(re.compile(rf"\b1\s*<<\s*{gen.MAX_BODY.bit_length() - 1}\b"))
    return pats


def test_no_signing_limit_is_spelled_outside_generated() -> None:
    """No hand-written file carries a literal of the spec's body or idempotency-key limit: they are
    read from ``generated/signing.py`` so a changed limit reaches the SDK by regeneration alone."""
    pats = _limit_patterns()
    offenders = []
    for path in _hand_written():
        text = re.sub(r"(?<=\d)_(?=\d)", "", path.read_text("utf-8"))
        offenders += [f"{path.relative_to(ROOT)}: {p.pattern}" for p in pats if p.search(text)]
    assert offenders == []
