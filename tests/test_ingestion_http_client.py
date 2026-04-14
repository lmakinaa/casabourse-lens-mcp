from __future__ import annotations

import ssl
from pathlib import Path

import certifi
import httpx
import pytest

pytest.importorskip("trading_tools.corporate_actions")

from ingestion.http.client import PoliteClient, _build_ssl_context

pytestmark = pytest.mark.v2_only


def test_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, request=request, json={"error": "temporary"})
        return httpx.Response(200, request=request, json={"ok": True})

    with PoliteClient(transport=httpx.MockTransport(handler), min_interval=0.0) as client:
        client._get_json_with_retry.retry.sleep = lambda _seconds: None
        out = client.get_json("https://api.example.test/data")

    assert out == {"ok": True}
    assert calls["n"] == 3


def test_does_not_retry_on_4xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, request=request, json={"error": "missing"})

    with PoliteClient(transport=httpx.MockTransport(handler), min_interval=0.0) as client:
        client._get_json_with_retry.retry.sleep = lambda _seconds: None
        with pytest.raises(httpx.HTTPStatusError):
            client.get_json("https://api.example.test/missing")

    assert calls["n"] == 1


def test_rate_limit_pacing(monkeypatch):
    ticks = iter([100.0, 100.2, 101.0])
    sleeps: list[float] = []

    monkeypatch.setattr("ingestion.http.client.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("ingestion.http.client.time.sleep", lambda seconds: sleeps.append(seconds))

    with PoliteClient(min_interval=1.0) as client:
        monkeypatch.setattr(client, "_get_json_with_retry", lambda url, params: {"ok": True})
        client.get_json("https://api.example.test/data")
        client.get_json("https://api.example.test/data")

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.8, rel=1e-3)


def test_client_uses_ssl_context_not_verify_false(monkeypatch):
    captured: dict = {}

    class FakeHttpxClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self):
            return None

    monkeypatch.setattr("ingestion.http.client.httpx.Client", FakeHttpxClient)

    client = PoliteClient()
    client.close()

    assert "verify" in captured
    assert isinstance(captured["verify"], ssl.SSLContext)
    assert captured["verify"] is not False


def test_extra_ca_file_is_loaded_into_context(tmp_path):
    base = ssl.create_default_context(cafile=certifi.where())

    src = (
        Path(__file__).resolve().parents[1]
        / "ingestion"
        / "http"
        / "ca_extras"
        / "sectigo_public_server_auth_ca_dv_r36.pem"
    )
    pem = tmp_path / "extra.pem"
    pem.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    ctx = _build_ssl_context([pem])

    def has_r36(context: ssl.SSLContext) -> bool:
        for cert in context.get_ca_certs():
            for rdn in cert.get("subject", ()):  # tuple[tuple[(k,v)]]
                for key, value in rdn:
                    if key == "commonName" and "R36" in value:
                        return True
        return False

    # Explicitly loaded in the augmented context.
    assert has_r36(ctx)
    # Baseline context can be either way depending on certifi version,
    # but augmented must not have fewer certs.
    assert len(ctx.get_ca_certs()) >= len(base.get_ca_certs())
