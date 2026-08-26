"""Client configuration, money maths and the status vocabulary."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from oblodai import Oblodai
from oblodai import config as config_module
from oblodai.config import resolve_config
from oblodai.core.errors import ConfigError
from oblodai.helpers import (
    add_amounts,
    amount_equals,
    compare_amounts,
    is_payment_final,
    is_payment_paid,
    is_payment_underpaid,
    is_payout_final,
    is_payout_succeeded,
    is_zero_amount,
    subtract_amounts,
)


def test_reads_credentials_and_base_url_from_the_environment() -> None:
    config = resolve_config(
        env={
            "OBLODAI_PUBLIC_ID": "pk",
            "OBLODAI_SECRET": "s",
            "OBLODAI_BASE_URL": "https://x.test/",
        }
    )
    assert config.credentials is not None
    assert (config.credentials.public_id, config.credentials.secret) == ("pk", "s")
    assert config.base_url == "https://x.test"


def test_the_client_reads_exactly_six_environment_variables() -> None:
    """One key pair, one admin token, and the three knobs - nothing else is honoured.

    Pinned because a variable the SDK silently stopped reading (or quietly started reading) is
    a credential that ends up somewhere its owner did not expect.
    """
    source = Path(config_module.__file__).read_text("utf-8")
    honoured = set(re.findall(r'environ\.get\("(OBLODAI_[A-Z_]+)"\)', source))
    assert honoured == {
        "OBLODAI_PUBLIC_ID",
        "OBLODAI_SECRET",
        "OBLODAI_ADMIN_TOKEN",
        "OBLODAI_BASE_URL",
        "OBLODAI_LOG",
        "OBLODAI_ALLOW_INSECURE",
    }


def test_a_stale_payout_pair_in_the_environment_changes_nothing() -> None:
    """The 1.2 variables may still sit in somebody's .env; they must not resurrect a second key."""
    config = resolve_config(
        env={
            "OBLODAI_PUBLIC_ID": "pk",
            "OBLODAI_SECRET": "s",
            "OBLODAI_PAYOUT_PUBLIC_ID": "wk",
            "OBLODAI_PAYOUT_SECRET": "s2",
        }
    )
    assert config.credentials is not None
    assert config.credentials.public_id == "pk"
    assert not hasattr(config, "payout_credentials")


def test_refuses_plain_http_except_for_loopback_or_when_allowed() -> None:
    with pytest.raises(ConfigError, match="https"):
        resolve_config(base_url="http://api.oblodai.com", env={})
    assert (
        resolve_config(base_url="http://localhost:8093", env={}).base_url == "http://localhost:8093"
    )
    assert resolve_config(base_url="http://[::1]:8093", env={}).base_url == "http://[::1]:8093"
    assert (
        resolve_config(base_url="http://10.0.0.1", allow_insecure_base_url=True, env={}).base_url
        == "http://10.0.0.1"
    )
    with pytest.raises(ConfigError, match="not a valid URL"):
        resolve_config(base_url="not-a-url", env={})


def test_refuses_half_a_key_pair() -> None:
    with pytest.raises(ConfigError, match="together"):
        resolve_config(public_id="pk", env={})
    with pytest.raises(ConfigError, match="together"):
        resolve_config(secret="s", env={})
    with pytest.raises(ConfigError):
        Oblodai(public_id="pk", base_url="https://api.test", env={})


def test_the_admin_token_falls_back_to_the_environment() -> None:
    assert resolve_config(env={"OBLODAI_ADMIN_TOKEN": "adm"}).admin_token == "adm"


def test_money_helpers_work_at_arbitrary_precision() -> None:
    assert add_amounts("0.1", "0.2") == "0.3"
    assert add_amounts("10.000000", "0.5") == "10.500000"
    assert subtract_amounts("1", "1.000001") == "-0.000001"
    assert compare_amounts("25", "25.000000") == 0
    assert compare_amounts("0.000000000000000001", "0") == 1
    assert compare_amounts("1", "2") == -1
    assert amount_equals("25", "25.0000")
    assert is_zero_amount("0.000000")
    with pytest.raises(ValueError, match="not a decimal amount"):
        add_amounts("1e9", "1")


def test_status_helpers_follow_the_core_vocabulary() -> None:
    assert is_payment_paid("paid_over")
    assert not is_payment_paid("wrong_amount")
    assert is_payment_underpaid("wrong_amount")
    assert not is_payment_final("confirm_check")
    assert is_payment_final("expired")
    assert not is_payout_final("sent")
    assert is_payout_final("confirmed")
    assert is_payout_succeeded("confirmed")
