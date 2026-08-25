"""Live tier: the SDK against a REAL core.

Set ``OBLODAI_LIVE_URL`` (e.g. ``http://127.0.0.1:8095``) to enable it; without it every live test
is skipped. Onboarding is open on a dev stand: ``POST /v1/merchants`` then
``POST /v1/merchants/{id}/sandbox`` mints a sandbox key pair.
"""

from __future__ import annotations

import os
import time
from typing import Dict

import httpx
import pytest

LIVE_URL = os.environ.get("OBLODAI_LIVE_URL")

pytestmark = pytest.mark.skipif(not LIVE_URL, reason="OBLODAI_LIVE_URL is not set")


def onboard_sandbox(base: str, label: str) -> Dict[str, str]:
    """Create a merchant and its dev store; returns the sandbox key pair and the merchant id."""
    with httpx.Client(timeout=30.0) as http:
        merchant = http.post(
            f"{base}/v1/merchants",
            json={"email": f"{label}-{int(time.time() * 1000)}@example.com", "name": label},
        ).json()
        merchant_id = merchant["result"]["merchant_id"]
        sandbox = http.post(f"{base}/v1/merchants/{merchant_id}/sandbox", json={}).json()
    key = sandbox["result"]["api_key"]
    return {
        "public_id": key["public_id"],
        "secret": key["secret"],
        "merchant_id": sandbox["result"]["merchant_id"],
    }


@pytest.fixture(scope="session")
def live_url() -> str:
    if not LIVE_URL:
        pytest.skip("OBLODAI_LIVE_URL is not set")
    return LIVE_URL
