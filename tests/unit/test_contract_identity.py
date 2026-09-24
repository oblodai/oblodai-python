"""Which contract the package was generated from is itself generated: no hand-kept snapshot."""

from __future__ import annotations

import hashlib
import json

import pytest

import oblodai
import oblodai.contract
from oblodai.generated import contract as generated
from tests.support.fixtures import backend_spec_path


def test_the_public_identity_is_the_generated_one() -> None:
    assert oblodai.CONTRACT_HASH == generated.CONTRACT_HASH
    assert oblodai.CONTRACT_VERSION == generated.CONTRACT_VERSION
    assert oblodai.contract.CONTRACT_HASH == generated.CONTRACT_HASH
    assert len(generated.CONTRACT_HASH) == 64


def test_the_identity_is_the_spec_the_code_was_generated_from() -> None:
    path = backend_spec_path()
    if not path.is_file():
        pytest.skip("backend openapi.json not found (set OBLODAI_BACKEND)")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == generated.CONTRACT_HASH
    assert json.loads(raw)["info"]["version"] == generated.CONTRACT_VERSION
