"""The coverage ledger: one SDK call per route the core declares.

Kept beside the tests rather than inside one, because two suites drive it - the wiring check in
``tests/contract/test_routes.py`` and the request-body check in ``test_wire_bodies.py``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from oblodai import Oblodai

__all__ = ["COVERAGE", "Call"]

#: One call per route.
#:
#: Typed against the synchronous client, but it drives both tiers: the async client is
#: structurally identical (same namespaces, same method names, same arguments), only its methods
#: return awaitables. The async test simply awaits whatever comes back, so a single table stays
#: the single source of truth for both tiers.
Call = Callable[[Oblodai], Any]

COVERAGE: Dict[str, Call] = {
    "GET /v1/claim/{token}": lambda ob: ob.payout_links.claim_preview("tok"),
    "GET /v1/currencies": lambda ob: ob.catalog.currencies(),
    "GET /v1/documents/balance": lambda ob: ob.documents.balance_certificate(),
    "GET /v1/documents/batch": lambda ob: ob.documents.batch_report("b1"),
    "GET /v1/documents/fees": lambda ob: ob.documents.fee_schedule(),
    "GET /v1/documents/jobs/file": lambda ob: ob.documents.job_file("j1"),
    "GET /v1/documents/ledger": lambda ob: ob.documents.ledger(),
    "GET /v1/documents/link": lambda ob: ob.documents.link_report("l1"),
    "GET /v1/documents/referrals": lambda ob: ob.documents.referrals_report(),
    "GET /v1/documents/split": lambda ob: ob.documents.split_report("i1"),
    "GET /v1/documents/statement": lambda ob: ob.documents.statement(
        {"from": "2026-01-01", "to": "2026-02-01"}
    ),
    "GET /v1/documents/wallet/statement": lambda ob: ob.documents.wallet_statement("w1"),
    "GET /v1/documents/{kind}/{id}": lambda ob: ob.documents.download(
        "invoice", "i1", {"exp": 1, "sig": "s"}
    ),
    "GET /v1/link/{id}": lambda ob: ob.payment_links.public_view("l1"),
    "GET /v1/pay/{id}": lambda ob: ob.payments.public_view("i1"),
    "GET /v1/pay/{id}/qr": lambda ob: ob.payments.public_qr("i1"),
    "GET /v1/sandbox/webhooks": lambda ob: ob.sandbox.webhooks(),
    "POST /v1/api-allowlist/add": lambda ob: ob.settings.add_api_allowlist("10.0.0.0/8"),
    "POST /v1/api-allowlist/enable": lambda ob: ob.settings.enable_api_allowlist(True),
    "POST /v1/api-allowlist/list": lambda ob: ob.settings.list_api_allowlist(),
    "POST /v1/api-allowlist/remove": lambda ob: ob.settings.remove_api_allowlist("10.0.0.0/8"),
    "POST /v1/auto-withdraw/delete": lambda ob: ob.settings.delete_auto_withdraw("USDT"),
    "POST /v1/auto-withdraw/list": lambda ob: ob.settings.list_auto_withdraw(),
    "POST /v1/auto-withdraw/set": lambda ob: ob.settings.set_auto_withdraw(
        {"currency": "USDT", "network": "tron", "address": "T"}
    ),
    "POST /v1/balance": lambda ob: ob.account.balance(),
    "POST /v1/batch/info": lambda ob: ob.batches.info({"batch_id": "b1"}),
    "POST /v1/claim/{token}": lambda ob: ob.payout_links.claim("tok", {"address": "T"}),
    "POST /v1/exchange-rate/list": lambda ob: ob.catalog.exchange_rates(),
    "POST /v1/link/{id}/checkout": lambda ob: ob.payment_links.checkout("l1"),
    "POST /v1/pay/{id}/select": lambda ob: ob.payments.select(
        "i1", {"currency": "USDT", "network": "tron"}
    ),
    "POST /v1/payment": lambda ob: ob.payments.create({"amount": "1", "currency": "USDT"}),
    "POST /v1/payment/accepted/list": lambda ob: ob.settings.list_accepted(),
    "POST /v1/payment/accepted/set": lambda ob: ob.settings.set_accepted({"accepted": []}),
    "POST /v1/payment/accuracy/get": lambda ob: ob.settings.get_accuracy(),
    "POST /v1/payment/accuracy/set": lambda ob: ob.settings.set_accuracy({"enabled": True}),
    "POST /v1/payment/autorefund/get": lambda ob: ob.settings.get_auto_refund(),
    "POST /v1/payment/autorefund/set": lambda ob: ob.settings.set_auto_refund(
        {"overpay": True, "underpay": False}
    ),
    "POST /v1/payment/batch": lambda ob: ob.payments.batch({"payments": []}),
    "POST /v1/payment/cancel": lambda ob: ob.payments.cancel({"uuid": "i1"}),
    "POST /v1/payment/discount/list": lambda ob: ob.settings.list_discounts(),
    "POST /v1/payment/discount/set": lambda ob: ob.settings.set_discount({"discount_percent": 1}),
    "POST /v1/payment/fee-config/get": lambda ob: ob.settings.get_payment_fee_config(),
    "POST /v1/payment/fee-config/set": lambda ob: ob.settings.set_payment_fee_config(
        {"payer_pays_percent": 50}
    ),
    "POST /v1/payment/history": lambda ob: ob.payments.history(),
    "POST /v1/payment/info": lambda ob: ob.payments.info({"uuid": "i1"}),
    "POST /v1/payment/link": lambda ob: ob.payment_links.create(
        {"amount_mode": "open", "currency": "USDT"}
    ),
    "POST /v1/payment/link/info": lambda ob: ob.payment_links.info("l1"),
    "POST /v1/payment/link/list": lambda ob: ob.payment_links.list(),
    "POST /v1/payment/link/toggle": lambda ob: ob.payment_links.toggle("l1", False),
    "POST /v1/payment/qr": lambda ob: ob.payments.qr({"uuid": "i1"}),
    "POST /v1/payment/refund": lambda ob: ob.refunds.create({"uuid": "i1"}),
    "POST /v1/payment/resend": lambda ob: ob.payments.resend({"uuid": "i1"}),
    "POST /v1/payment/resolve": lambda ob: ob.refunds.resolve({"action": "accept", "uuid": "i1"}),
    "POST /v1/payment/send-email": lambda ob: ob.payments.send_email({"uuid": "i1"}),
    "POST /v1/payment/services": lambda ob: ob.payments.services(),
    "POST /v1/payment/testing-webhook": lambda ob: ob.webhooks.test_legacy({"url": "https://x"}),
    "POST /v1/payout": lambda ob: ob.payouts.create(
        {"amount": "1", "currency": "USDT", "address": "T", "order_id": "o"}
    ),
    "POST /v1/payout/approve": lambda ob: ob.payouts.approve("p1"),
    "POST /v1/payout/batch": lambda ob: ob.payouts.batch({"payouts": []}),
    "POST /v1/payout/calculate": lambda ob: ob.payouts.calculate(
        {"amount": "1", "currency": "USDT"}
    ),
    "POST /v1/payout/cancel": lambda ob: ob.payouts.cancel("p1"),
    "POST /v1/payout/fee-config/get": lambda ob: ob.payouts.get_fee_config(),
    "POST /v1/payout/fee-config/set": lambda ob: ob.payouts.set_fee_config(
        {"fee_on_recipient": True}
    ),
    "POST /v1/payout/history": lambda ob: ob.payouts.history(),
    "POST /v1/payout/info": lambda ob: ob.payouts.info({"uuid": "p1"}),
    "POST /v1/payout/link": lambda ob: ob.payout_links.create(
        {"amount": "1", "currency": "USDT", "network": "tron"}
    ),
    "POST /v1/payout/link/batch": lambda ob: ob.payout_links.batch({"items": []}),
    "POST /v1/payout/link/cancel": lambda ob: ob.payout_links.cancel("l1"),
    "POST /v1/payout/link/cheque": lambda ob: ob.payout_links.cheque({"claim_token": "t"}),
    "POST /v1/payout/link/info": lambda ob: ob.payout_links.info("l1"),
    "POST /v1/payout/link/list": lambda ob: ob.payout_links.list(),
    "POST /v1/payout/mass": lambda ob: ob.payouts.mass({"payouts": []}),
    "POST /v1/payout/refund-fee-config/get": lambda ob: ob.payouts.get_refund_fee_config(),
    "POST /v1/payout/refund-fee-config/set": lambda ob: ob.payouts.set_refund_fee_config(
        {"fee_on_customer": True}
    ),
    "POST /v1/payout/services": lambda ob: ob.payouts.services(),
    "POST /v1/payout/validate": lambda ob: ob.payouts.validate(
        {"amount": "1", "currency": "USDT", "address": "T", "order_id": "o"}
    ),
    "POST /v1/referral/info": lambda ob: ob.account.referral(),
    "POST /v1/refund/batch": lambda ob: ob.refunds.batch({"refunds": []}),
    "POST /v1/sandbox/deposit": lambda ob: ob.sandbox.deposit({"invoice_id": "i1"}),
    "POST /v1/sandbox/faucet": lambda ob: ob.sandbox.faucet({"asset": "USDT", "amount": "1"}),
    "POST /v1/sandbox/reset": lambda ob: ob.sandbox.reset(),
    "POST /v1/sandbox/webhooks/replay": lambda ob: ob.sandbox.replay("d1"),
    "POST /v1/split/config/get": lambda ob: ob.splits.get_config(),
    "POST /v1/split/config/set": lambda ob: ob.splits.set_config({"refund_hold_seconds": 60}),
    "POST /v1/split/recipient/optin": lambda ob: ob.splits.set_opt_in(True),
    "POST /v1/split/recipient/optin/get": lambda ob: ob.splits.get_opt_in(),
    "POST /v1/split/rule": lambda ob: ob.splits.create_rule({"percent": "10"}),
    "POST /v1/split/rule/delete": lambda ob: ob.splits.delete_rule("r1"),
    "POST /v1/split/rule/list": lambda ob: ob.splits.list_rules(),
    "POST /v1/test-webhook/payment": lambda ob: ob.webhooks.test(
        "payment", {"url_callback": "https://x"}
    ),
    "POST /v1/test-webhook/payout": lambda ob: ob.webhooks.test(
        "payout", {"url_callback": "https://x"}
    ),
    "POST /v1/test-webhook/wallet": lambda ob: ob.webhooks.test(
        "wallet", {"url_callback": "https://x"}
    ),
    "POST /v1/transfer/batch": lambda ob: ob.transfers.batch({}),
    "POST /v1/transfer/to-personal": lambda ob: ob.transfers.to_personal(
        {"amount": "1", "currency": "USDT"}
    ),
    "POST /v1/transfer/to-user": lambda ob: ob.transfers.to_user(
        {"amount": "1", "currency": "USDT", "to_user_id": "u"}
    ),
    "POST /v1/vrcs": lambda ob: ob.account.vrcs(),
    "POST /v1/wallet": lambda ob: ob.wallets.create({"currency": "USDT", "network": "tron"}),
    "POST /v1/wallet/block": lambda ob: ob.wallets.block({"address": "T"}),
    "POST /v1/wallet/blocked-address-refund": lambda ob: ob.wallets.refund_blocked_deposit(
        {"uuid": "w1", "address": "T"}
    ),
    "POST /v1/wallet/qr": lambda ob: ob.wallets.qr("T"),
    "POST /v1/webhooks": lambda ob: ob.webhooks.register("https://x"),
    "POST /v1/webhooks/deliveries": lambda ob: ob.webhooks.deliveries(),
    "POST /v1/webhooks/rotate-secret": lambda ob: ob.webhooks.rotate_secret(),
    "POST /v1/documents/jobs": lambda ob: ob.documents.create_job({"kind": "statement"}),
    "POST /v1/documents/jobs/info": lambda ob: ob.documents.job_info("j1"),
    "POST /v1/merchants": lambda ob: ob.merchants.create({"email": "a@b.c", "name": "A"}),
    "POST /v1/merchants/{id}/sandbox": lambda ob: ob.merchants.create_sandbox("m1"),
}
