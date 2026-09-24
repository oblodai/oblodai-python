"""A webhook receiver, on the standard library alone.

    OBLODAI_WEBHOOK_SECRET=whsec_... python examples/webhook_receiver.py
    # then point url_callback at http://<host>:8099/oblodai/webhook

The four rules that matter, whichever framework you use:

1. Verify over the RAW request bytes. A re-serialized parse will not match the signature.
2. Deduplicate on `X-Webhook-Event-Id` (`delivery.event_id`) - it is the same for every retry AND
   every resend of a state; `X-Webhook-Id` changes on a resend.
3. Drop out-of-order deliveries with `webhooks.is_stale(event, last_sequence)`; a retried `paid`
   can arrive after a newer state.
4. Answer a rehearsal delivery (`delivery.is_test`) with 2xx, but never act on it as if money
   moved - it is signed like a live one and nothing happened on chain.

Answer 2xx quickly: the gateway retries anything else for about 26 hours.

`SignatureError` and `WebhookPayloadError` are deliberately different: the first means the body
is not from the gateway, the second that an authentic delivery carried something this receiver
cannot read. Both answer 4xx here, but only the first is a security event.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Mapping, Optional, Set

from oblodai import SignatureError, WebhookPayloadError, webhooks

SECRET = os.environ["OBLODAI_WEBHOOK_SECRET"]
# During a rotation keep the outgoing secret here for at least 26 h.
PREVIOUS_SECRET = os.environ.get("OBLODAI_WEBHOOK_SECRET_PREVIOUS")

seen_events: Set[str] = set()
last_sequence: Dict[str, int] = {}


def object_key(event: Mapping[str, object]) -> str:
    """The object the event is about: its kind and the id the contract names for that kind."""
    return f"{event['type']}:{webhooks.object_id(event)}"


def handle(event: Dict[str, object], event_id: Optional[str]) -> None:
    """Your business logic. Runs once per state, in order, for each object."""
    kind = event["type"]
    status = event["status"]
    print(f"[{event_id}] {object_key(event)} -> {status}")
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
            self.send_response(401)
            self.end_headers()
            self.wfile.write(err.code.encode())
            return
        except WebhookPayloadError as err:
            # Authentic, but unreadable: 400, and no retry will fix it - look at the payload.
            self.send_response(400)
            self.end_headers()
            self.wfile.write(err.code.encode())
            return

        event = delivery.event
        obj = object_key(event)
        # A core that does not send the event id yet leaves the delivery id as the next best key.
        key = delivery.event_id or delivery.id
        if delivery.is_test:
            pass  # a rehearsal delivery (`webhooks.test`, sandbox): acknowledge, touch nothing
        elif key and key in seen_events:
            pass  # a retry or a resend of a state already processed
        elif webhooks.is_stale(event, last_sequence.get(obj)):
            pass  # an older state arriving after a newer one
        else:
            handle(dict(event), delivery.event_id)
            if key:
                seen_events.add(key)
            sequence = event.get("sequence")
            # Only remember a sequence the delivery actually carried: `int(None)` here would turn
            # a missing field into a crashed handler and a delivery the gateway keeps retrying.
            if isinstance(sequence, int) and not isinstance(sequence, bool):
                last_sequence[obj] = sequence

        # 2xx even for duplicates: the work is done, stop the retries.
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt: str, *args: object) -> None:
        return None


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
