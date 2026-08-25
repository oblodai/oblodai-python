# Examples

Each script runs on its own. Install the SDK first (`pip install oblodai`, or `pip install -e ..`
from a checkout) and export your keys — a **sandbox key** (`test_…`) is the right one to start with.

```bash
export OBLODAI_PUBLIC_ID=test_...
export OBLODAI_SECRET=...
# a local or self-hosted gateway:
# export OBLODAI_BASE_URL=http://127.0.0.1:8095
```

| script | what it shows |
| ------ | ------------- |
| [`sandbox.py`](sandbox.py) | the whole money path in the sandbox: invoice → simulated deposit → faucet → payout → webhook log |
| [`accept_payment.py`](accept_payment.py) | create an invoice, show the payer where to send, settle it (including an underpayment) |
| [`payout.py`](payout.py) | quote the fee, dry-run the payout, send it with your own idempotency key |
| [`webhook_receiver.py`](webhook_receiver.py) | a signature-verifying receiver on the standard library: raw-byte verification, deduplication, out-of-order guard |

```bash
python examples/sandbox.py
OBLODAI_WEBHOOK_SECRET=whsec_... python examples/webhook_receiver.py
```
