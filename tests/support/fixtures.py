"""Loaders for the shared contract data in ``contract/``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

CONTRACT_DIR = Path(__file__).resolve().parent.parent.parent / "contract"


def load_contract() -> Dict[str, Any]:
    """``contract.json``: routes, enums, error codes, signing and webhook vectors."""
    data: Dict[str, Any] = json.loads((CONTRACT_DIR / "contract.json").read_text("utf-8"))
    return data


def load_fixtures() -> Dict[str, Dict[str, Any]]:
    """Golden response bodies, keyed by route (``"POST /v1/payment"``)."""
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted((CONTRACT_DIR / "fixtures").glob("*.json")):
        fixture = json.loads(path.read_text("utf-8"))
        out[fixture["route"]] = fixture
    return out


def fixture(route: str) -> Dict[str, Any]:
    found = load_fixtures().get(route)
    if found is None:
        raise KeyError(f"no fixture for {route}")
    return found


def result_of(route: str) -> Any:
    """The recorded success ``result`` for a route (raises when the recording was a refusal)."""
    found = fixture(route)
    if not 200 <= found["status"] < 300:
        raise AssertionError(f"fixture for {route} is a refusal ({found['status']})")
    return found.get("response", {}).get("result")


def load_webhook_samples() -> List[Dict[str, Any]]:
    """Real signed deliveries: ``headers``, parsed ``body`` and the exact ``raw`` bytes."""
    data: List[Dict[str, Any]] = json.loads(
        (CONTRACT_DIR / "webhook-samples.json").read_text("utf-8")
    )
    return data


def load_error_samples() -> Dict[str, Dict[str, Any]]:
    """Recorded error envelopes, keyed by error code."""
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted((CONTRACT_DIR / "errors").glob("*.json")):
        out[path.stem] = json.loads(path.read_text("utf-8"))
    return out
