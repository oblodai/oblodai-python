"""The whole money path in the sandbox, end to end, in about a second.

    OBLODAI_PUBLIC_ID=test_... OBLODAI_SECRET=... python examples/sandbox.py

A sandbox key drives a chainless copy of the gateway: a faucet instead of a wallet, simulated
deposits instead of blocks, and real signed webhooks. Nothing here touches a chain.
"""

from __future__ import annotations

import uuid

from oblodai import Oblodai, is_payment_paid


def main() -> None:
    oblodai = Oblodai()

    invoice = oblodai.payments.create(
        {
            "amount": "25",
            "currency": "USDT",
            "network": "tron",
            "order_id": f"demo-{uuid.uuid4()}",
        }
    )
    print(f"1. invoice {invoice['uuid']} for {invoice['payer_amount']} {invoice['payer_currency']}")

    oblodai.sandbox.deposit(
        {
            "invoice_id": invoice["uuid"],
            "amount": "25",
            "confirmations": 20,
            "txid": f"demo-tx-{uuid.uuid4()}",
        }
    )
    paid = oblodai.payments.get(invoice["uuid"])
    print(
        f"2. simulated deposit -> status {paid['status']} (paid={is_payment_paid(paid['status'])})"
    )

    oblodai.sandbox.faucet({"asset": "USDT", "amount": "100"})
    balance = oblodai.account.balance()
    usdt = next(b for b in balance["balance"]["merchant"] if b["currency"] == "USDT")
    print(f"3. faucet -> balance {usdt['balance']} USDT")

    payout = oblodai.payouts.create(
        {
            "amount": "10",
            "currency": "USDT",
            "network": "tron",
            "address": "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx",
            "order_id": f"demo-po-{uuid.uuid4()}",
        }
    )
    print(f"4. payout {payout['uuid']} status={payout['status']}")

    for delivery in oblodai.sandbox.webhooks(limit=5):
        print(f"5. webhook {delivery['event_type']} -> {delivery['status']}")

    print(f"6. reset: {oblodai.sandbox.reset()}")
    oblodai.close()


if __name__ == "__main__":
    main()
