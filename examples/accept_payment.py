"""Accept a payment: create an invoice, show the payer where to send, wait for it to settle.

    OBLODAI_PUBLIC_ID=... OBLODAI_SECRET=... python examples/accept_payment.py

In production you do not poll: the gateway calls your `url_callback` (see webhook_receiver.py).
Polling is here so the example runs on its own.
"""

from __future__ import annotations

import time
import uuid

from oblodai import Oblodai, is_payment_final, is_payment_paid
from oblodai.contract.requests import PaymentBody


def main() -> None:
    oblodai = Oblodai()  # reads OBLODAI_PUBLIC_ID / OBLODAI_SECRET / OBLODAI_BASE_URL

    body: PaymentBody = {
        "amount": "25",  # decimal string, never a float
        "currency": "USDT",  # price in a fiat (USD, EUR, ...) or a crypto asset
        "network": "tron",  # omit to let the payer choose on the pay page
        "order_id": f"order-{uuid.uuid4()}",  # your reference; idempotent per order_id
        "url_callback": "https://shop.example/oblodai/webhook",
        "url_success": "https://shop.example/thanks",
    }
    invoice = oblodai.payments.create(body)

    print(f"invoice {invoice['uuid']} -> {invoice['url']}")
    print(f"send {invoice['payer_amount']} {invoice['payer_currency']} to {invoice['address']}")
    if invoice.get("memo") or invoice.get("destination_tag"):
        print(
            f"the network needs a memo/tag: {invoice.get('memo') or invoice.get('destination_tag')}"
        )

    deadline = time.time() + 120
    while time.time() < deadline:
        current = oblodai.payments.get(invoice["uuid"])
        print(f"  status={current['status']} paid={current['amount_paid']}")
        if is_payment_final(current["status"]):
            if is_payment_paid(current["status"]):
                print("paid - release the goods")
            elif current["status"] == "wrong_amount":
                # Underpaid: keep what arrived, or send it back.
                resolved = oblodai.refunds.resolve({"uuid": invoice["uuid"], "action": "accept"})
                print(f"underpayment resolved: {resolved}")
            else:
                print(f"finished as {current['status']}")
            break
        time.sleep(5)

    oblodai.close()


if __name__ == "__main__":
    main()
