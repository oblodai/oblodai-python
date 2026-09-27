"""A webhook receiver, on the standard library alone.

    OBLODAI_WEBHOOK_SECRET=whsec_... python examples/webhook_receiver.py
    # then point url_callback at http://<host>:8099/oblodai/webhook

The rules that matter, whichever framework you use:

1. Verify over the RAW request bytes. A re-serialized parse will not match the signature.
2. Decide on the SIGNED body only. The delivery id, event id, event and test headers are not
   signed, so anyone who captured a delivery can resend it with other values in them.
3. Always ignore a rehearsal delivery (`delivery.is_test`, from the body's `test: true`): answer
   2xx, but never act on it as if money moved - it is signed like a live one.
4. Deduplicate on `delivery.event_key`: dedupe on event_id (fallback type:id:sequence), both from
   the signed body; drop out-of-order deliveries with `webhooks.is_stale(event, last_sequence)`.
5. A resend of a state keeps its event_id, but a delivery from an older core has none and its
   resend carries a new sequence: make the action itself idempotent per object and status
   (below: `acted`), so a second `paid` never ships the goods twice.

Answer 2xx quickly: the gateway retries anything else for about 26 hours.

`SignatureError` and `WebhookPayloadError` are deliberately different: the first means the body
is not from the gateway, the second that an authentic delivery carried something this receiver
cannot read. Both answer 4xx here, but only the first is a security event.
"""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Mapping, Optional, Set, Tuple

from oblodai import SignatureError, WebhookPayloadError, webhooks

SECRET = os.environ["OBLODAI_WEBHOOK_SECRET"]
# During a rotation keep the outgoing secret here for at least 26 h.
PREVIOUS_SECRET = os.environ.get("OBLODAI_WEBHOOK_SECRET_PREVIOUS")

seen_events: Set[str] = set()
last_sequence: Dict[str, int] = {}
#: (object, status) pairs already acted on: a resend of `paid` must not ship twice.
acted: Set[Tuple[str, object]] = set()


def object_key(event: Mapping[str, object]) -> str:
    """The object the event is about: its kind and the id the contract names for that kind."""
    return f"{event['type']}:{webhooks.object_id(event)}"


def handle(event: Dict[str, object], key: Optional[str]) -> None:
    """Your business logic. Runs once per state, in order, for each object."""
    kind = event["type"]
    status = event["status"]
    obj = object_key(event)
    if (obj, status) in acted:
        return  # a resend of a state already acted on
    acted.add((obj, status))
    print(f"[{key}] {obj} -> {status}")
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
        # From the signed body: never from the (unsigned) event-id or delivery-id headers.
        key = delivery.event_key
        if delivery.is_test:
            pass  # a rehearsal delivery (`webhooks.test`, sandbox): acknowledge, touch nothing
        elif key and key in seen_events:
            pass  # a retry, or a replay of a delivery already processed
        elif webhooks.is_stale(event, last_sequence.get(obj)):
            pass  # an older state arriving after a newer one
        else:
            handle(dict(event), key)
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
