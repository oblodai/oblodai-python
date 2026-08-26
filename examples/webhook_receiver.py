"""A webhook receiver, on the standard library alone.

    OBLODAI_WEBHOOK_SECRET=whsec_... python examples/webhook_receiver.py
    # then point url_callback at http://<host>:8099/oblodai/webhook

The three rules that matter, whichever framework you use:

1. Verify over the RAW request bytes. A re-serialized parse will not match the signature.
2. Deduplicate on `X-Webhook-Id` - it is stable across retries of the same delivery.
3. Drop out-of-order deliveries with `webhooks.is_stale(event, last_sequence)`; a retried `paid`
   can arrive after a newer state.
4. Answer a rehearsal delivery (`delivery.is_test`) with 2xx, but never act on it as if money
   moved - it is signed like a live one and nothing happened on chain.

Answer 2xx quickly: the gateway retries anything else for about 26 hours.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Set

from oblodai import SignatureError, webhooks

SECRET = os.environ["OBLODAI_WEBHOOK_SECRET"]
# During a rotation keep the outgoing secret here for at least 26 h.
PREVIOUS_SECRET = os.environ.get("OBLODAI_WEBHOOK_SECRET_PREVIOUS")

seen_deliveries: Set[str] = set()
last_sequence: Dict[str, int] = {}


def handle(event: Dict[str, object], delivery_id: Optional[str]) -> None:
    """Your business logic. Runs once per delivery, in order, for each object."""
    kind = event["type"]
    uuid = str(event["uuid"])
    status = event["status"]
    print(f"[{delivery_id}] {kind} {uuid} -> {status}")
    if kind == "payment" and status in ("paid", "paid_over"):
        ...  # release the goods
    elif kind == "payout" and status == "confirmed":
        ...  # mark the withdrawal as settled


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # BaseHTTPRequestHandler names it this way
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        try:
            delivery = webhooks.verify_delivery(
                raw, self.headers, secret=SECRET, previous_secret=PREVIOUS_SECRET
            )
        except SignatureError as err:
            # Never act on an unverified body.
            self.send_response(400)
            self.end_headers()
            self.wfile.write(err.code.encode())
            return

        event = delivery.event
        object_id = str(event["uuid"])
        if delivery.is_test:
            pass  # a rehearsal delivery (`webhooks.test`, sandbox): acknowledge, touch nothing
        elif delivery.id and delivery.id in seen_deliveries:
            pass  # a retry of something already processed
        elif webhooks.is_stale(event, last_sequence.get(object_id)):
            pass  # an older state arriving after a newer one
        else:
            handle(dict(event), delivery.id)
            if delivery.id:
                seen_deliveries.add(delivery.id)
            last_sequence[object_id] = int(event["sequence"])

        # 2xx even for duplicates: the work is done, stop the retries.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt: str, *args: object) -> None:
        return None


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
