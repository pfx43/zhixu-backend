"""TCN register 建档：客户端同步调用 + 注册路径写入 user_hash。"""
from __future__ import annotations

import httpx
import pytest

from app.services.auth.auth_service import AuthManager
from app.services.tcn.tcn_client import TCNClient


@pytest.fixture()
def fresh_client(monkeypatch):
    """每个用例用独立客户端，避免单例污染。"""
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_ENABLED", True)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_API_KEY", "test-key")
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_BASE_URL", "http://tcn.test")
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_ADMIN_TOKEN", "")
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_TIMEOUT", 2)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_MAX_RETRIES", 0)

    TCNClient._instance = None
    client = TCNClient()
    client._MAX_RETRIES = 0
    yield client
    TCNClient._instance = None


def test_register_user_sync_posts_user_hash(fresh_client, monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True, "user_hash": "abc"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)

    result = fresh_client.register_user_sync("abc123hash")
    assert result.get("ok") is True
    assert seen["url"].endswith("/v1/user/register")
    assert "abc123hash" in seen["body"]
    assert seen["headers"].get("x-api-key") == "test-key"


def test_register_user_sync_degrades_without_raising(fresh_client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "X-Api-Key header is required"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", fake_client)

    result = fresh_client.register_user_sync("abc123hash")
    assert result.get("_degraded") is True
    assert result.get("ok") is False


def test_archive_helper_swallows_errors(monkeypatch):
    calls = []

    class FakeClient:
        def register_user_sync(self, user_hash: str):
            calls.append(user_hash)
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.services.tcn.tcn_client.tcn_client",
        FakeClient(),
    )
    AuthManager._archive_tcn_user("hash-x", context="test")
    assert calls == ["hash-x"]


def test_gen_user_hash_stable_for_user_id():
    a = AuthManager._gen_user_hash(42)
    b = AuthManager._gen_user_hash(42)
    assert a == b
    assert len(a) == 32
