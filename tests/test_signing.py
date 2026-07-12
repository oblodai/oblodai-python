"""Тесты подписи запросов и проверки вебхуков."""

import hashlib
import hmac
import time

import pytest

from oblodai import (
    OblodaiSignatureError,
    compute_webhook_signature,
    construct_event,
    sign_request,
    verify_webhook,
)


def test_sign_request_canonical_string():
    secret = "test_secret"
    body = '{"amount":"25.00"}'
    ts = "1700000000"

    signed = sign_request(secret, "POST", "/v1/payment", body, timestamp=ts)

    expected = hmac.new(
        secret.encode(), f"1700000000\nPOST\n/v1/payment\n{body}".encode(), hashlib.sha256
    ).hexdigest()

    assert signed.signature == expected
    assert signed.timestamp == ts
    assert signed.body == body


def test_sign_request_auto_timestamp():
    before = int(time.time())
    signed = sign_request("s", "POST", "/v1/balance", "{}")
    after = int(time.time())
    assert before <= int(signed.timestamp) <= after


class TestVerifyWebhook:
    secret = "wh_secret"

    def _sign(self, ts: str, body: str) -> str:
        return compute_webhook_signature(self.secret, ts, body)

    def test_accepts_valid_fresh(self):
        ts = str(int(time.time()))
        body = '{"type":"payment","status":"paid"}'
        sig = self._sign(ts, body)
        headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig}
        assert verify_webhook(self.secret, body, headers) is True

    def test_rejects_bad_signature(self):
        ts = str(int(time.time()))
        headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": "deadbeef"}
        with pytest.raises(OblodaiSignatureError):
            verify_webhook(self.secret, '{"status":"paid"}', headers)

    def test_rejects_non_ascii_signature(self):
        # Не-ASCII в заголовке подписи не должен ронять TypeError из hmac.compare_digest —
        # ожидаем штатную OblodaiSignatureError (fail-closed).
        ts = str(int(time.time()))
        headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": "подпись"}
        with pytest.raises(OblodaiSignatureError):
            verify_webhook(self.secret, '{"status":"paid"}', headers)

    def test_rejects_stale_replay(self):
        old = str(int(time.time()) - 3600)
        body = '{"status":"paid"}'
        sig = self._sign(old, body)
        headers = {"X-Webhook-Timestamp": old, "X-Webhook-Signature": sig}
        with pytest.raises(OblodaiSignatureError):
            verify_webhook(self.secret, body, headers, max_age_seconds=300)

    def test_allows_stale_when_disabled(self):
        old = str(int(time.time()) - 3600)
        body = '{"status":"paid"}'
        sig = self._sign(old, body)
        headers = {"X-Webhook-Timestamp": old, "X-Webhook-Signature": sig}
        assert verify_webhook(self.secret, body, headers, max_age_seconds=0) is True

    def test_bytes_body(self):
        ts = str(int(time.time()))
        body = b'{"status":"paid"}'
        sig = compute_webhook_signature(self.secret, ts, body)
        headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig}
        assert verify_webhook(self.secret, body, headers) is True

    def test_case_insensitive_headers(self):
        ts = str(int(time.time()))
        body = '{"status":"paid"}'
        sig = self._sign(ts, body)
        headers = {"x-webhook-timestamp": ts, "x-webhook-signature": sig}
        assert verify_webhook(self.secret, body, headers) is True

    def test_construct_event_returns_parsed(self):
        ts = str(int(time.time()))
        body = '{"type":"payment","status":"paid","uuid":"abc"}'
        sig = self._sign(ts, body)
        headers = {"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig}
        event = construct_event(self.secret, body, headers)
        assert event["uuid"] == "abc"
        assert event["status"] == "paid"
