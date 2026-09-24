"""Loaders for the recorded data in ``contract/`` (golden bodies, error samples, signed webhook
deliveries) and for the signing vectors of the backend spec's ``x-oblodai-signing``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

CONTRACT_DIR = Path(__file__).resolve().parent.parent.parent / "contract"


def backend_spec_path() -> Path:
    """The backend's ``openapi.json`` (``$OBLODAI_BACKEND``, else ``../oblodai-backend``)."""
    from scripts.check_generated import backend_root

    return backend_root() / "services" / "core" / "api" / "openapi.json"


def load_signing() -> Optional[Dict[str, Any]]:
    """``x-oblodai-signing`` of the backend spec — the one source of the signing vectors — or
    ``None`` when there is no backend checkout (an error when ``$OBLODAI_BACKEND`` names one)."""
    path = backend_spec_path()
    if not path.is_file():
        if os.environ.get("OBLODAI_BACKEND"):
            raise RuntimeError(f"backend openapi.json not found at {path}")
        return None
    signing: Dict[str, Any] = json.loads(path.read_text("utf-8"))["x-oblodai-signing"]
    return signing


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
