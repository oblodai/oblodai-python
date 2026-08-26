"""Send money out: quote the fee, dry-run the payout, then create it.

    OBLODAI_PUBLIC_ID=... OBLODAI_SECRET=... python examples/payout.py

Money out is signed with the merchant's one API key, exactly like money in.
"""

from __future__ import annotations

import uuid

from oblodai import Oblodai, OblodaiError, is_payout_final
from oblodai.contract.requests import PayoutBody

ADDRESS = "TQrY8bkbpXKPt2LZbU8jqfnpFbUSF15sbx"


def main() -> None:
    oblodai = Oblodai()  # OBLODAI_PUBLIC_ID / OBLODAI_SECRET

    quote = oblodai.payouts.calculate({"amount": "10", "currency": "USDT", "network": "tron"})
    print(f"commission {quote['commission']} {quote['currency']}, bearer {quote['fee_bearer']}")

    dry_run = oblodai.payouts.validate(
        {"amount": "10", "currency": "USDT", "network": "tron", "address": ADDRESS}
    )
    if not dry_run["valid"]:
        print("the payout would be refused")
        return
    if dry_run["maturity_note"]:
        print(f"note: {dry_run['maturity_note']}")

    body: PayoutBody = {
        "amount": "10",
        "currency": "USDT",
        "network": "tron",
        "address": ADDRESS,
        "order_id": f"payout-{uuid.uuid4()}",
    }
    try:
        # Your own key survives a process restart: a re-run of this script cannot pay twice.
        payout = oblodai.payouts.create(body, idempotency_key=f"payout-{body['order_id']}")
    except OblodaiError as err:
        # `retryable` is the gateway's own verdict - the SDK already retried what it should.
        print(f"refused: {err.code} ({err.message}); retryable={err.retryable}")
        return

    print(f"payout {payout['uuid']} status={payout['status']} txid={payout['txid'] or '-'}")
    if not is_payout_final(payout["status"]):
        print("watch for the payout.* webhook, or poll payouts.get(payout['uuid'])")

    oblodai.close()


if __name__ == "__main__":
    main()
