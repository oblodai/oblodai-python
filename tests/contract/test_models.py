"""Wire models versus the golden bodies the core recorded.

Each row names a route, how to reach the object inside its ``result`` and the model's key tuple.
Keys must match EXACTLY: a field the core stopped sending fails here, and so does a field it
started sending that the model lacks. Fields that are genuinely conditional on the wire are listed
as optional and tolerated on either side.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple

import pytest

from oblodai.contract import models as M
from oblodai.contract.enums import (
    DELIVERY_STATUSES,
    ERROR_CODES,
    EVENT_TYPES,
    PAYMENT_STATUSES,
    PAYOUT_LINK_STATUSES,
    PAYOUT_STATUSES,
)
from tests.support.fixtures import (
    load_contract,
    load_error_samples,
    load_fixtures,
    load_webhook_samples,
    result_of,
)

#: ``(route, picker over the recorded ``result``, expected keys, keys tolerated on either side)``.
Row = Tuple[str, Callable[[Any], Any], Sequence[str], Sequence[str]]


def row(
    route: str,
    pick: Callable[[Any], Any],
    keys: Sequence[str],
    optional: Sequence[str] = (),
) -> Row:
    return (route, pick, keys, optional)


ROWS: List[Row] = [
    row("POST /v1/payment", lambda r: r, M.PAYMENT_KEYS),
    row("POST /v1/payment/info", lambda r: r, M.PAYMENT_KEYS, ["refunds", "refund_status"]),
    row("POST /v1/payment/cancel", lambda r: r, M.PAYMENT_KEYS),
    row("POST /v1/payment/history", lambda r: r["items"][0], M.PAYMENT_KEYS),
    row("GET /v1/pay/{id}", lambda r: r, M.PUBLIC_PAYMENT_KEYS),
    row("POST /v1/pay/{id}/select", lambda r: r, M.PUBLIC_PAYMENT_KEYS),
    row("POST /v1/link/{id}/checkout", lambda r: r, M.PUBLIC_PAYMENT_KEYS),
    row("POST /v1/payment/qr", lambda r: r, M.QR_CODE_KEYS),
    row("GET /v1/pay/{id}/qr", lambda r: r, M.QR_CODE_KEYS),
    row("POST /v1/payment/services", lambda r: r["items"][0], M.SERVICE_METHOD_KEYS),
    row("POST /v1/payout/services", lambda r: r["items"][0], M.SERVICE_METHOD_KEYS),
    row("POST /v1/payment/batch", lambda r: r, M.BATCH_SUBMITTED_KEYS),
    row("POST /v1/payout/batch", lambda r: r, M.BATCH_SUBMITTED_KEYS),
    row("POST /v1/refund/batch", lambda r: r, M.BATCH_SUBMITTED_KEYS),
    row("POST /v1/transfer/batch", lambda r: r, M.BATCH_SUBMITTED_KEYS),
    row("POST /v1/batch/info", lambda r: r, M.BATCH_INFO_KEYS),
    row("POST /v1/payout", lambda r: r, M.PAYOUT_KEYS),
    row("POST /v1/payout/info", lambda r: r, M.PAYOUT_KEYS, ["error", "error_code"]),
    row("POST /v1/payout/cancel", lambda r: r, M.PAYOUT_KEYS),
    row("POST /v1/payout/history", lambda r: r["items"][0], M.PAYOUT_KEYS),
    row("POST /v1/payout/mass", lambda r: r["items"][0]["result"], M.PAYOUT_KEYS),
    row("POST /v1/payment/refund", lambda r: r, M.PAYOUT_KEYS),
    row("POST /v1/payout/calculate", lambda r: r, M.PAYOUT_CALCULATION_KEYS),
    row("POST /v1/payout/validate", lambda r: r, M.PAYOUT_VALIDATION_KEYS),
    row("POST /v1/payout/link", lambda r: r, M.PAYOUT_LINK_KEYS, ["claim_token", "claim_url"]),
    row("POST /v1/payout/link/info", lambda r: r, M.PAYOUT_LINK_KEYS),
    row("POST /v1/payout/link/list", lambda r: r["items"][0], M.PAYOUT_LINK_KEYS),
    row("POST /v1/payout/link/cancel", lambda r: r, M.PAYOUT_LINK_KEYS),
    row(
        "POST /v1/payout/link/batch",
        lambda r: r["items"][0]["result"],
        M.PAYOUT_LINK_KEYS,
        ["claim_token", "claim_url", "batch_id"],
    ),
    row("GET /v1/claim/{token}", lambda r: r, M.CLAIM_PREVIEW_KEYS),
    row("POST /v1/claim/{token}", lambda r: r, M.CLAIM_RESULT_KEYS),
    row("POST /v1/payment/link", lambda r: r, M.PAYMENT_LINK_CREATED_KEYS),
    row("POST /v1/payment/link/info", lambda r: r, M.PAYMENT_LINK_KEYS, ["payments"]),
    row("POST /v1/payment/link/list", lambda r: r["items"][0], M.PAYMENT_LINK_KEYS),
    row("GET /v1/link/{id}", lambda r: r, M.PUBLIC_PAYMENT_LINK_KEYS),
    row("POST /v1/balance", lambda r: r, M.BALANCE_KEYS),
    row("POST /v1/referral/info", lambda r: r, M.REFERRAL_INFO_KEYS),
    row("POST /v1/auto-withdraw/list", lambda r: r["items"][0], M.AUTO_WITHDRAW_RULE_KEYS),
    row("POST /v1/api-allowlist/list", lambda r: r, M.API_ALLOWLIST_KEYS),
    row("POST /v1/payment/discount/list", lambda r: r["items"][0], M.DISCOUNT_RULE_KEYS),
    row("POST /v1/split/rule/list", lambda r: r["items"][0], M.SPLIT_RULE_KEYS),
    row("GET /v1/currencies", lambda r: r, M.CURRENCIES_KEYS),
    row(
        "GET /v1/currencies",
        lambda r: r["currencies"][0]["networks"][0],
        M.CURRENCY_NETWORK_KEYS,
        ["contract"],
    ),
    row("POST /v1/exchange-rate/list", lambda r: r["items"][0], M.EXCHANGE_RATE_KEYS),
    row("POST /v1/webhooks", lambda r: r, M.WEBHOOK_ENDPOINT_KEYS),
    row("POST /v1/webhooks/rotate-secret", lambda r: r, M.WEBHOOK_SECRET_ROTATED_KEYS),
    row("POST /v1/webhooks/deliveries", lambda r: r["items"][0], M.WEBHOOK_DELIVERY_KEYS),
    row(
        "GET /v1/sandbox/webhooks",
        lambda r: r["items"][0],
        M.WEBHOOK_DELIVERY_KEYS,
        ["payload", "sequence"],
    ),
    row("POST /v1/payment/resolve", lambda r: r, [*M.PAYOUT_KEYS, "resolution"]),
    row("POST /v1/payment/send-email", lambda r: r, M.EMAIL_SENT_KEYS),
    row("POST /v1/payment/resend", lambda r: r, M.OK_RESULT_KEYS),
    row("POST /v1/payment/accepted/set", lambda r: r, M.OK_RESULT_KEYS),
    row("POST /v1/split/rule/delete", lambda r: r, M.OK_RESULT_KEYS),
    row(
        "POST /v1/payment/accepted/list",
        lambda r: r["items"][0],
        M.ACCEPTED_METHOD_KEYS,
        ["reason"],
    ),
    row("POST /v1/payment/accuracy/get", lambda r: r, M.ACCURACY_CONFIG_KEYS),
    row("POST /v1/payment/accuracy/set", lambda r: r, M.ACCURACY_CONFIG_KEYS),
    row("POST /v1/payment/autorefund/get", lambda r: r, M.AUTO_REFUND_CONFIG_KEYS),
    row("POST /v1/payment/autorefund/set", lambda r: r, M.AUTO_REFUND_CONFIG_KEYS, ["configured"]),
    row("POST /v1/payment/discount/set", lambda r: r, M.DISCOUNT_RULE_KEYS),
    row("POST /v1/payment/fee-config/get", lambda r: r, M.PAYMENT_FEE_CONFIG_KEYS),
    row("POST /v1/payment/fee-config/set", lambda r: r, M.PAYMENT_FEE_CONFIG_KEYS, ["enabled"]),
    row("POST /v1/payout/fee-config/get", lambda r: r, M.PAYOUT_FEE_CONFIG_KEYS),
    row("POST /v1/payout/fee-config/set", lambda r: r, M.PAYOUT_FEE_CONFIG_KEYS, ["configured"]),
    row("POST /v1/payout/refund-fee-config/get", lambda r: r, M.REFUND_FEE_CONFIG_KEYS),
    row(
        "POST /v1/payout/refund-fee-config/set",
        lambda r: r,
        M.REFUND_FEE_CONFIG_KEYS,
        ["configured"],
    ),
    row("POST /v1/payment/link/toggle", lambda r: r, M.PAYMENT_LINK_TOGGLED_KEYS),
    row("POST /v1/split/rule", lambda r: r, M.SPLIT_RULE_CREATED_KEYS),
    row("POST /v1/split/config/get", lambda r: r, M.SPLIT_CONFIG_KEYS),
    row("POST /v1/split/config/set", lambda r: r, M.SPLIT_CONFIG_KEYS),
    row("POST /v1/split/recipient/optin", lambda r: r, M.SPLIT_OPT_IN_KEYS),
    row("POST /v1/split/recipient/optin/get", lambda r: r, M.SPLIT_OPT_IN_KEYS),
    row("POST /v1/vrcs", lambda r: r, M.VRCS_STATUS_KEYS),
    row("POST /v1/auto-withdraw/set", lambda r: r["items"][0], M.AUTO_WITHDRAW_RULE_KEYS),
    row("POST /v1/auto-withdraw/delete", lambda r: r, ["items"]),
    row("POST /v1/api-allowlist/add", lambda r: r, M.API_ALLOWLIST_KEYS),
    row("POST /v1/api-allowlist/remove", lambda r: r, M.API_ALLOWLIST_KEYS),
    row("POST /v1/api-allowlist/enable", lambda r: r, M.API_ALLOWLIST_KEYS),
    row(
        "POST /v1/wallet",
        lambda r: r,
        M.WALLET_KEYS,
        ["destination_tag", "memo", "address_xaddress", "address_muxed"],
    ),
    row("POST /v1/wallet/block", lambda r: r, M.WALLET_BLOCKED_KEYS),
    row("POST /v1/wallet/qr", lambda r: r, ["image"]),
    row("POST /v1/wallet/blocked-address-refund", lambda r: r, [*M.PAYOUT_KEYS, "wallet_uuid"]),
    row("POST /v1/transfer/to-personal", lambda r: r, M.TRANSFER_TO_PERSONAL_KEYS),
    row("POST /v1/transfer/to-user", lambda r: r, M.TRANSFER_TO_USER_KEYS),
    row(
        "POST /v1/documents/jobs",
        lambda r: r,
        M.DOCUMENT_JOB_KEYS,
        ["ready_within", "file", "error"],
    ),
    row(
        "POST /v1/documents/jobs/info",
        lambda r: r,
        M.DOCUMENT_JOB_KEYS,
        ["ready_within", "file", "error"],
    ),
    row(
        "POST /v1/documents/jobs/info",
        lambda r: r["file"],
        ["download_url", "expires_at", "rows", "size_bytes"],
    ),
    row("POST /v1/test-webhook/payment", lambda r: r, M.WEBHOOK_TEST_RESULT_KEYS),
    row("POST /v1/test-webhook/payout", lambda r: r, M.WEBHOOK_TEST_RESULT_KEYS),
    row("POST /v1/test-webhook/wallet", lambda r: r, M.WEBHOOK_TEST_RESULT_KEYS),
    row(
        "POST /v1/payment/testing-webhook",
        lambda r: r,
        [*M.WEBHOOK_TEST_RESULT_KEYS, "url", "duration_ms"],
    ),
    row("POST /v1/sandbox/faucet", lambda r: r, M.FAUCET_RESULT_KEYS),
    row("POST /v1/sandbox/deposit", lambda r: r, M.SANDBOX_DEPOSIT_KEYS),
    row("POST /v1/sandbox/reset", lambda r: r, M.SANDBOX_RESET_KEYS),
    row("POST /v1/sandbox/webhooks/replay", lambda r: r, M.SANDBOX_REPLAY_KEYS),
    row("POST /v1/merchants", lambda r: r, M.MERCHANT_ONBOARDED_KEYS),
    row("POST /v1/merchants", lambda r: r["api_key"], ["public_id", "secret", "kind"]),
    row("POST /v1/merchants/{id}/sandbox", lambda r: r, M.SANDBOX_STORE_KEYS),
]

#: Routes the API guarantees to refuse for API keys (no success body exists to model).
#: API-key payouts auto-approve; approve serves the cabinet's maker-checker flow.
NOT_MODELLED = {"POST /v1/payout/approve"}


def key_set_diff(
    actual: Sequence[str], expected: Sequence[str], optional: Sequence[str] = ()
) -> Dict[str, List[str]]:
    """What the wire is missing versus the model, and what it carries the model does not know."""
    have, want, tolerated = set(actual), set(expected), set(optional)
    return {
        "missing_on_wire": sorted(want - have - tolerated),
        "unknown_on_wire": sorted(have - want - tolerated),
    }


NO_DRIFT: Dict[str, List[str]] = {"missing_on_wire": [], "unknown_on_wire": []}

FIXTURES = load_fixtures()


@pytest.mark.parametrize(
    ("route", "pick", "keys", "optional"),
    ROWS,
    ids=[f"{r[0]} <-> {len(r[2])} keys" for r in ROWS],
)
def test_model_keys_match_the_golden_body(
    route: str, pick: Callable[[Any], Any], keys: Sequence[str], optional: Sequence[str]
) -> None:
    recorded = FIXTURES.get(route)
    if recorded is None or recorded["status"] >= 300:
        pytest.skip(f"{route}: recorded as a refusal in this environment, nothing to compare")
    obj = pick(recorded.get("response", {}).get("result"))
    assert obj, f"{route}: picker found nothing"
    diff = key_set_diff(list(obj), keys, optional)
    assert diff == NO_DRIFT, f"{route}: model keys drifted from the wire"


def test_every_recorded_success_body_has_a_model_row() -> None:
    covered = {r[0] for r in ROWS}
    for route, recorded in FIXTURES.items():
        if not 200 <= recorded["status"] < 300 or route in NOT_MODELLED:
            continue
        if "json" not in (recorded.get("headers") or {}).get("Content-Type", ""):
            continue
        assert route in covered, f"{route}: recorded success body has no model row"


def test_statuses_in_fixtures_are_in_the_vocabulary() -> None:
    for payment in result_of("POST /v1/payment/history")["items"]:
        assert payment["status"] in PAYMENT_STATUSES
    for payout in result_of("POST /v1/payout/history")["items"]:
        assert payout["status"] in PAYOUT_STATUSES
    for link in result_of("POST /v1/payout/link/list")["items"]:
        assert link["status"] in PAYOUT_LINK_STATUSES
    for delivery in result_of("POST /v1/webhooks/deliveries")["items"]:
        assert delivery["status"] in DELIVERY_STATUSES


def test_webhook_samples_carry_known_events_and_modelled_bodies() -> None:
    event_keys: Dict[str, Sequence[str]] = {
        "payment": M.PAYMENT_EVENT_KEYS,
        "payout": M.PAYOUT_EVENT_KEYS,
        "wallet": M.WALLET_EVENT_KEYS,
    }
    samples = load_webhook_samples()
    assert samples, "no webhook samples recorded"
    for sample in samples:
        assert sample["headers"]["X-Webhook-Event"] in EVENT_TYPES
        body = sample["body"]
        assert key_set_diff(list(body), event_keys[body["type"]], ["test"]) == NO_DRIFT


def test_every_recorded_error_code_has_the_documented_envelope() -> None:
    for code, recorded in load_error_samples().items():
        assert code in ERROR_CODES
        error = recorded.get("response", {}).get("error", {})
        assert error["code"] == code
        assert isinstance(error["retryable"], bool)
        assert isinstance(error["request_id"], str)
        if recorded["status"] == 429:
            assert error["retry_after"] > 0


def test_recorded_request_bodies_only_use_documented_fields() -> None:
    schemas = {
        f"{r['method']} {r['path']}": r.get("request_schema") for r in load_contract()["routes"]
    }
    for route, recorded in FIXTURES.items():
        schema = schemas.get(route)
        body = recorded.get("request")
        if not schema or not schema.get("properties") or not isinstance(body, dict):
            continue
        for field in body:
            assert field in schema["properties"], (
                f"{route}: journey sent undocumented field {field!r}"
            )


# --- the Python stand-in for the reference's compile-time `defineKeys` check -----------------


def _keys_constants() -> Dict[Tuple[str, ...], List[str]]:
    """Every ``*_KEYS`` tuple the models package exports, indexed by its value."""
    out: Dict[Tuple[str, ...], List[str]] = {}
    for name in dir(M):
        if name.endswith("_KEYS"):
            out.setdefault(tuple(getattr(M, name)), []).append(name)
    return out


def _typed_dict_name(keys_constant: str) -> str:
    """``PAYMENT_LINK_KEYS`` -> ``PaymentLink``."""
    return "".join(word.capitalize() for word in keys_constant[: -len("_KEYS")].split("_"))


KEYS_CONSTANTS = _keys_constants()


@pytest.mark.parametrize(
    ("keys", "route"), [(tuple(r[2]), r[0]) for r in ROWS], ids=[r[0] for r in ROWS]
)
def test_key_tuple_agrees_with_its_typed_dict(keys: Tuple[str, ...], route: str) -> None:
    """A key tuple may never name a field its ``TypedDict`` does not declare.

    The TypeScript SDK gets this for free from ``defineKeys<T>()``; Python's ``TypedDict`` carries
    the same information at runtime, in ``__required_keys__`` / ``__optional_keys__``.
    """
    names = KEYS_CONSTANTS.get(keys)
    if not names:
        pytest.skip(f"{route}: inline key list, no exported model to compare against")
    checked = 0
    for name in names:
        model: Any = getattr(M, _typed_dict_name(name), None)
        if not hasattr(model, "__required_keys__"):
            continue  # a key tuple with no TypedDict of its own (a narrower create/toggle result)
        checked += 1
        known = set(model.__required_keys__) | set(model.__optional_keys__)
        assert set(keys) <= known, f"{name}: names fields {_typed_dict_name(name)} does not declare"
    if checked == 0:
        pytest.skip(f"{route}: {names} has no matching TypedDict")
