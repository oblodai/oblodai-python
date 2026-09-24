"""Live sweep: every namespace against a real core.

The point is not the business outcome but that the bodies the SDK sends are accepted (no 400 from
our own shapes) and the bodies that come back decode (no ContractError). Routes that need a
subsystem the stand may lack (documents, email, static wallets) are probed and tolerated when the
core reports them disabled.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterator, Optional, TypeVar

import pytest

from oblodai import (
    ContractError,
    NotFoundError,
    Oblodai,
    PaymentView,
    PayoutLinkCreated,
    ValidationError,
)
from tests.live.conftest import onboard_sandbox

pytestmark = pytest.mark.skipif(
    not os.environ.get("OBLODAI_LIVE_URL"), reason="OBLODAI_LIVE_URL is not set"
)

ADDR = "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx"
HOOK = os.environ.get("OBLODAI_LIVE_HOOK_URL", "http://127.0.0.1:8096/hook")

T = TypeVar("T")


def stamp() -> int:
    return int(time.time() * 1000)


def accept(call: Callable[[], T]) -> Optional[T]:
    """Fail on SDK-side contract/shape problems; tolerate business refusals (409/403/404)."""
    try:
        return call()
    except (ContractError, ValidationError):
        raise
    except Exception:
        return None


class Stand:
    """One onboarded dev store plus the objects the sweep reuses."""

    def __init__(self, base: str) -> None:
        key = onboard_sandbox(base, "sweep")
        self.api = Oblodai(
            public_id=key["public_id"],
            secret=key["secret"],
            base_url=base,
            allow_insecure_base_url=True,
        )
        self.public = Oblodai(base_url=base, allow_insecure_base_url=True)
        self.api.sandbox.faucet(asset="USDT", amount="1000")
        # A per-invoice url_callback needs a registered endpoint (it signs with its secret).
        self.api.webhooks.register(url=HOOK)
        self.invoice: PaymentView = self.api.payments.create(
            amount="25",
            currency="USDT",
            network="tron",
            order_id=f"sw-{stamp()}",
            payer_email="buyer@example.com",
            url_callback=HOOK,
        )
        self.payout_link: Optional[PayoutLinkCreated] = None
        self.documents_enabled = True
        try:
            self.api.documents.get_balance()
        except NotFoundError as err:
            if err.code == "document.disabled":
                self.documents_enabled = False

    def close(self) -> None:
        self.api.close()
        self.public.close()


@pytest.fixture(scope="module")
def stand(live_url: str) -> Iterator[Stand]:
    built = Stand(live_url)
    yield built
    built.close()


def test_catalog_and_account(stand: Stand) -> None:
    assert len(stand.public.checkout.list_currencies().currencies) > 0
    assert stand.public.account.list_exchange_rates(currency_from="BTC").items is not None
    assert stand.api.account.get_balance().balance.merchant is not None
    assert isinstance(stand.api.referrals.get_info().code, str)
    assert isinstance(stand.api.settings.configure_vrcs().enabled, bool)
    assert isinstance(stand.api.settings.configure_vrcs(enabled=False).enabled, bool)


def test_payments_lookups_qr_services_public_checkout_batch(stand: Stand) -> None:
    api, invoice = stand.api, stand.invoice
    assert api.payments.get_info(uuid=invoice.uuid).uuid == invoice.uuid
    # Sandbox invoices carry a synthetic `sandbox:` address, which the core deliberately does not
    # render into a QR - the fields come back empty. A real invoice returns a data URI.
    assert isinstance(api.payments.get_qr(uuid=invoice.uuid).image, str)
    assert len(api.payments.list_services(limit=5).items) > 0
    assert stand.public.checkout.get(invoice.uuid).status == "created"
    assert isinstance(stand.public.checkout.get_qr(invoice.uuid).image, str)

    multi = api.payments.create(amount="10", currency="USDT", order_id=f"sw-multi-{stamp()}")
    selected = stand.public.checkout.select_method(multi.uuid, currency="USDT", network="tron")
    assert selected is not None

    accept(lambda: api.webhooks.resend_payment(uuid=invoice.uuid))
    accept(lambda: api.payments.send_email(uuid=invoice.uuid))

    # A batch is a long-running operation: the runtime returns a Job (Ruling 3), which the
    # generated signature does not know about yet.
    batch: Any = api.batches.create_payment(
        on_error="continue",
        payments=[
            {"amount": "5", "currency": "USDT", "network": "tron", "order_id": f"sw-b-{stamp()}"}
        ],
    )
    assert batch.id
    assert api.batches.get_info(batch_id=batch.id).batch_id == batch.id

    to_cancel = api.payments.create(
        amount="5", currency="USDT", network="tron", order_id=f"sw-c-{stamp()}"
    )
    assert api.payments.cancel(uuid=to_cancel.uuid).status == "cancelled"
    for payment in api.payments.list_history(limit=2):
        assert payment.uuid
        break


def test_deposit_paid_refund_resolve_refund_batch(stand: Stand) -> None:
    api, invoice = stand.api, stand.invoice
    api.sandbox.simulate_deposit(
        invoice_id=invoice.uuid, amount="25", confirmations=20, txid=f"sw-tx-{stamp()}"
    )
    assert api.payments.get_info(uuid=invoice.uuid).status in ("paid", "confirm_check")
    accept(
        lambda: api.refunds.payment(
            uuid=invoice.uuid, address=ADDR, amount="5", reference=f"sw-r-{stamp()}"
        )
    )
    accept(lambda: api.payments.resolve(uuid=invoice.uuid, action="accept"))
    accept(
        lambda: api.batches.create_refund(
            refunds=[
                {
                    "uuid": invoice.uuid,
                    "address": ADDR,
                    "amount": "5",
                    "reference": f"sw-rb-{stamp()}",
                }
            ]
        )
    )


def test_payouts_every_route(stand: Stand) -> None:
    api = stand.api
    assert api.payouts.calculate(amount="10", currency="USDT", network="tron").currency == "USDT"
    assert (
        api.payouts.validate(amount="10", currency="USDT", network="tron", address=ADDR).valid
        is True
    )
    payout = api.payouts.create(
        amount="10", currency="USDT", network="tron", address=ADDR, order_id=f"sw-po-{stamp()}"
    )
    assert api.payouts.get_info(order_id=str(payout.order_id)).uuid == payout.uuid
    accept(lambda: api.payouts.cancel(uuid=payout.uuid))
    accept(lambda: api.payouts.approve(uuid=payout.uuid))

    mass = api.payouts.create_mass(
        payouts=[
            {
                "amount": "5",
                "currency": "USDT",
                "network": "tron",
                "address": ADDR,
                "order_id": f"sw-m-{stamp()}",
            }
        ]
    )
    assert mass.items[0].idx == 0

    batch: Any = api.batches.create_payout(
        payouts=[
            {
                "amount": "5",
                "currency": "USDT",
                "network": "tron",
                "address": ADDR,
                "order_id": f"sw-pb-{stamp()}",
            }
        ]
    )
    assert batch.id
    assert len(api.payouts.list_services().items) > 0
    assert isinstance(
        api.settings.set_payout_fee_config(fee_on_recipient=True).fee_on_recipient, bool
    )
    assert isinstance(api.settings.get_payout_fee_config().fee_on_recipient, bool)
    assert isinstance(
        api.settings.set_refund_fee_config(fee_on_customer=True).fee_on_customer, bool
    )
    assert isinstance(api.settings.get_refund_fee_config().fee_on_customer, bool)
    assert api.payouts.list_history(kind="refund", limit=5).items is not None


def test_payout_links(stand: Stand) -> None:
    api = stand.api
    link = api.payout_links.create(
        amount="5",
        currency="USDT",
        network="tron",
        reference=f"sw-pl-{stamp()}",
        title="Bonus",
        expires_in_seconds=3600,
    )
    stand.payout_link = link
    assert link.claim_token
    assert api.payout_links.get(link_id=link.link_id).status == "funded"
    assert len(api.payout_links.list(limit=5).items) > 0
    preview = stand.public.payout_links.get_payout_claim(link.claim_token)
    assert getattr(preview, "claimable", None) is True
    claimed = stand.public.payout_links.claim_payout(link.claim_token, address=ADDR)
    assert claimed.payout_id

    second = api.payout_links.create(
        amount="5", currency="USDT", network="tron", reference=f"sw-pl2-{stamp()}"
    )
    assert api.payout_links.cancel(link_id=second.link_id).status == "cancelled"
    batch = api.payout_links.create_batch(
        items=[
            {"amount": "5", "currency": "USDT", "network": "tron", "reference": f"sw-plb-{stamp()}"}
        ]
    )
    assert batch.items[0].ok is True


def test_payment_links(stand: Stand) -> None:
    api = stand.api
    created = api.payment_links.create(
        title="Tip",
        amount_mode="fixed",
        currency="USDT",
        amount_fixed="10",
        pinned_network="tron",
    )
    assert created.link_id
    assert api.payment_links.get(link_id=created.link_id).active is True
    assert len(api.payment_links.list().items) > 0
    public_view = stand.public.checkout.get_public_payment_link(created.link_id)
    assert public_view.amount_mode == "fixed"
    checkout = stand.public.checkout.payment_link(created.link_id, currency="USDT", network="tron")
    assert checkout is not None
    assert api.payment_links.toggle(link_id=created.link_id, active=False).active is False


def test_splits_and_settings(stand: Stand) -> None:
    api = stand.api
    rule = api.splits.create_rule(percent="10", address=ADDR, network="tron", note="partner")
    assert any(r.rule_id == rule.rule_id for r in api.splits.list_rules().items)
    assert api.splits.set_config(refund_hold_seconds=3600).refund_hold_seconds == 3600
    assert api.splits.get_config().refund_hold_seconds == 3600
    assert api.splits.set_recipient_opt_in(enabled=True).enabled is True
    assert api.splits.get_recipient_opt_in().enabled is True
    assert api.splits.delete_rule(rule_id=rule.rule_id).ok is True

    discount = api.settings.set_discount(currency="USDT", network="tron", discount_percent=2)
    assert discount.discount_percent == 2
    assert len(api.settings.list_discounts().items) > 0
    assert api.settings.set_accuracy(enabled=True, accuracy_percent=2).enabled is True
    assert api.settings.get_accuracy().enabled is True
    assert api.settings.set_auto_refund(overpay=True, underpay=False).overpay is True
    assert isinstance(api.settings.get_auto_refund().configured, bool)
    accepted = api.settings.set_accepted_currencies(
        accepted=[{"currency": "USDT", "network": "tron"}]
    )
    assert accepted.ok is True
    assert api.settings.list_accepted_currencies().items is not None
    assert api.settings.set_payment_fee_config(payer_pays_percent=50).payer_pays_percent == 50
    assert api.settings.get_payment_fee_config().payer_pays_percent == 50

    rules = api.settings.set_auto_withdraw_rule(
        currency="USDT", network="tron", address=ADDR, min_amount="100"
    )
    assert len(rules.items) > 0
    assert api.settings.list_auto_withdraw_rules() is not None
    assert api.settings.delete_auto_withdraw_rule(currency="USDT") is not None

    assert "203.0.113.0/24" in api.api_allowlist.add_entry(cidr="203.0.113.0/24").items
    assert "203.0.113.0/24" in api.api_allowlist.list().items
    assert api.api_allowlist.set_enabled(enabled=False).enabled is False
    assert "203.0.113.0/24" not in api.api_allowlist.remove_entry(cidr="203.0.113.0/24").items


def test_webhooks_and_sandbox_inspector(stand: Stand) -> None:
    api = stand.api
    endpoint = api.webhooks.register(url=HOOK)
    assert endpoint.endpoint_id
    assert api.webhooks.rotate_secret().secret
    assert api.webhooks.list_deliveries(limit=5).items is not None
    accept(
        lambda: api.webhooks.send_test_payment(
            url_callback=HOOK, currency="USDT", network="tron", status="paid"
        )
    )
    accept(lambda: api.webhooks.send_legacy_test(url=HOOK, status="paid"))

    inspector = api.sandbox.list_webhooks().first()
    assert inspector.items is not None
    terminal = next((d for d in inspector.items if d.status in ("delivered", "dead")), None)
    if terminal:
        accept(lambda: api.sandbox.replay_webhook(delivery_id=terminal.id))


def test_wallets_and_transfers(stand: Stand) -> None:
    # Refused for a dev store, as documented; the point is that the SDK's shapes are accepted.
    api = stand.api
    accept(lambda: api.wallets.create(currency="USDT", network="tron", order_id=f"sw-w-{stamp()}"))
    accept(lambda: api.wallets.get_qr(address=ADDR))
    accept(lambda: api.wallets.block(address=ADDR))
    accept(lambda: api.payouts.transfer_to_personal(amount="5", currency="USDT"))


def test_documents(stand: Stand) -> None:
    if not stand.documents_enabled:
        pytest.skip("this stand has no document renderer")
    api = stand.api
    # openapi.json declares no query parameters for GET /v1/documents/* (period, format, lang,
    # the report's id), so only the reports that need none are swept here.
    statement = api.documents.get_statement()
    assert "pdf" in statement.content_type
    assert len(statement.content) > 0
    assert len(api.documents.get_fees().content) > 0
    assert api.documents.get_ledger().content_type is not None
    if stand.payout_link:
        cheque = api.documents.get_payout_link_cheque(
            claim_token=stand.payout_link.claim_token, lang="en"
        )
        assert "pdf" in cheque.content_type

    job: Any = api.documents.create_job(
        kind="statement", format="csv", lang="en", from_="2026-01-01", to="2026-08-25"
    )
    assert api.documents.get_job(job_id=job.id).job_id == job.id
    accept(lambda: job.download())


def test_sandbox_reset_last(stand: Stand) -> None:
    assert isinstance(stand.api.sandbox.reset().invoices_cancelled, int)
