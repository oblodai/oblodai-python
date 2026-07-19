"""Тесты требования https:// для базового URL и исключения для петлевых хостов.

Зачем правило. Каждый подписанный запрос несёт ``X-Signature`` — HMAC тела и пути на секрете
API-ключа. По ``http://`` он идёт открытым текстом: посредник читает подпись вместе с телом.
Раньше SDK принимал ``http://`` молча. Исключение — петлевой хост: трафик не покидает машину,
и на этом держатся локальные стенды (наш — ``http://localhost:8095``).
"""

import httpx
import pytest
import respx

from oblodai import AsyncOblodaiClient, OblodaiClient

# ── http на внешний хост — ошибка ──


@pytest.mark.parametrize("bad", [
    "http://api.oblodai.com",
    "http://api.oblodai.com:8095",
    "http://192.168.1.10:8095",       # частная сеть — всё ещё не петля
    "http://10.0.0.5",
    "http://127.0.0.1.evil.com",      # петлевой адрес лишь в начале имени
    "http://localhost.evil.com",      # и суффикс тоже не спасает
])
def test_plain_http_external_host_rejected(bad):
    with pytest.raises(ValueError) as sync_exc:
        OblodaiClient(public_id="p", secret="s", base_url=bad)
    assert "https://" in str(sync_exc.value)
    assert "localhost" in str(sync_exc.value), "в тексте названо исключение для петли"

    with pytest.raises(ValueError):
        AsyncOblodaiClient(public_id="p", secret="s", base_url=bad)


@pytest.mark.parametrize("bad", ["api.oblodai.com", "", "/v1", "localhost:8095"])
def test_url_without_scheme_rejected(bad):
    """URL без схемы/хоста — тоже ошибка: 'localhost:8095' urlsplit читает как схему 'localhost'."""
    with pytest.raises(ValueError) as exc:
        OblodaiClient(public_id="p", secret="s", base_url=bad)
    assert "абсолютным URL" in str(exc.value)


def test_other_schemes_rejected():
    for bad in ["ftp://api.oblodai.com", "ws://api.oblodai.com"]:
        with pytest.raises(ValueError):
            OblodaiClient(public_id="p", secret="s", base_url=bad)


# ── http на петлю — можно ──


@pytest.mark.parametrize("ok", [
    "http://localhost:8095",          # наш локальный стенд
    "http://localhost",
    "http://127.0.0.1:8095",
    "http://127.0.0.2:8095",          # вся 127.0.0.0/8 — петля
    "http://[::1]:8095",
    "http://dev.localhost:3000",
])
def test_plain_http_loopback_allowed(ok):
    client = OblodaiClient(public_id="p", secret="s", base_url=ok)
    assert client._http._base_url == ok, "URL сохраняется как передан, без нормализации"
    AsyncOblodaiClient(public_id="p", secret="s", base_url=ok)


@respx.mock
def test_loopback_stand_actually_works():
    """Локальный стенд по http продолжает обслуживаться — правило его не ломает."""
    route = respx.post("http://localhost:8095/v1/payment").mock(
        return_value=httpx.Response(200, json={"state": 0, "result": {
            "uuid": "p1", "order_id": "o1", "amount": "10.00", "currency": "USD",
            "payment_status": "check",
        }})
    )
    client = OblodaiClient(
        public_id="test_p", secret="oblodai_test_s", base_url="http://localhost:8095", retry=None
    )
    payment = client.payments.create(amount="10", currency="USD", order_id="o1")

    assert payment.uuid == "p1"
    assert route.calls[0].request.headers["X-Signature"], "запрос подписан как обычно"


# ── https — можно ──


@pytest.mark.parametrize("ok", [
    "https://api.oblodai.com",
    "https://api.oblodai.com/",
    "https://api.test",
    "HTTPS://api.oblodai.com",        # схема разбирается без учёта регистра
    "https://localhost:8095",
])
def test_https_allowed(ok):
    OblodaiClient(public_id="p", secret="s", base_url=ok)
    AsyncOblodaiClient(public_id="p", secret="s", base_url=ok)


def test_default_base_url_is_https():
    client = OblodaiClient(public_id="p", secret="s")
    assert client._http._base_url.startswith("https://")


def test_from_env_base_url_validated(monkeypatch):
    """Через окружение правило тоже действует — иначе OBLODAI_BASE_URL был бы дырой в обход."""
    monkeypatch.setenv("OBLODAI_PUBLIC_ID", "pub")
    monkeypatch.setenv("OBLODAI_SECRET", "sec")
    monkeypatch.setenv("OBLODAI_BASE_URL", "http://api.oblodai.com")
    with pytest.raises(ValueError) as exc:
        OblodaiClient.from_env()
    assert "https://" in str(exc.value)

    monkeypatch.setenv("OBLODAI_BASE_URL", "http://localhost:8095")
    assert OblodaiClient.from_env()._http._base_url == "http://localhost:8095"
