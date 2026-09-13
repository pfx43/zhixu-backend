"""TCN admin 图接口鉴权与熔断隔离。

回归背景：/admin/graph/domains 用错鉴权头（X-Admin-Token）返回 401，
重试耗尽后把全局 _enabled 置 False，导致 KT 读接口全部 503。
"""
from __future__ import annotations

import asyncio

import httpx

from app.services.tcn.tcn_client import TCNClient


class _Resp:
    def __init__(self, status_code: int = 200, data: dict | list | None = None):
        self.status_code = status_code
        self._data = data if data is not None else {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://tcn.test")
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )

    def json(self):
        return self._data


class _FakeAsyncClient:
    def __init__(self, response: _Resp):
        self.response = response
        self.calls: list[tuple] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get("headers")))
        return self.response

    async def aclose(self) -> None:
        pass


def _fresh_client(monkeypatch, *, admin_token: str = "jwt-admin", api_key: str = "svc-key"):
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_ENABLED", True)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_API_KEY", api_key)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_ADMIN_TOKEN", admin_token)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_BASE_URL", "http://tcn.test")
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_TIMEOUT", 2)
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_MAX_RETRIES", 0)

    TCNClient._instance = None
    client = TCNClient()
    client._MAX_RETRIES = 0
    return client


def _cleanup():
    TCNClient._instance = None


def test_admin_headers_use_bearer_not_x_admin_token(monkeypatch):
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_ADMIN_TOKEN", "jwt-admin")
    monkeypatch.setattr("app.services.tcn.tcn_client.TCN_API_KEY", "svc-key")

    admin_headers = TCNClient._admin_headers()
    assert admin_headers == {"Authorization": "Bearer jwt-admin"}

    user_headers = TCNClient._auth_headers()
    assert user_headers == {"X-Api-Key": "svc-key"}
    assert "X-Admin-Token" not in admin_headers


def test_get_graph_domains_sends_bearer(monkeypatch):
    client = _fresh_client(monkeypatch)
    fake = _FakeAsyncClient(_Resp(200, {"domains": []}))
    client._client = fake
    try:
        asyncio.run(client.get_graph_domains())
    finally:
        _cleanup()

    assert len(fake.calls) == 1
    url, headers = fake.calls[0]
    assert url == "/admin/graph/domains"
    assert headers == {"Authorization": "Bearer jwt-admin"}


def test_admin_failure_keeps_client_enabled(monkeypatch):
    """admin 图接口 401 不得熔断 /v1/user/* 通道。"""
    client = _fresh_client(monkeypatch)
    fake = _FakeAsyncClient(_Resp(401))
    client._client = fake
    client._enabled = True
    try:
        asyncio.run(client.get_graph_domains())
        assert client.is_enabled is True
    finally:
        _cleanup()


def test_user_404_is_empty_state_not_outage(monkeypatch):
    """未建档用户返回 404：不重试、不熔断，按空态降级。"""
    client = _fresh_client(monkeypatch)
    fake = _FakeAsyncClient(_Resp(404))
    client._client = fake
    client._enabled = True
    try:
        result = asyncio.run(client.get_summary("uhash"))
        assert result.get("_degraded") is True
        assert len(fake.calls) == 1  # 404 不重试
        assert client.is_enabled is True
    finally:
        _cleanup()


def test_user_failure_disables_client(monkeypatch):
    """user 通道真实失败仍应熔断，避免把坏状态一直透传。"""
    client = _fresh_client(monkeypatch)
    fake = _FakeAsyncClient(_Resp(500))
    client._client = fake
    client._enabled = True
    try:
        asyncio.run(client.get_profile("uhash"))
        assert client.is_enabled is False
    finally:
        _cleanup()


def test_graph_skips_call_without_admin_token(monkeypatch):
    """未配置 TCN_ADMIN_TOKEN 时不应空打 admin 接口（避免无谓 401 重试）。"""
    client = _fresh_client(monkeypatch, admin_token="")
    fake = _FakeAsyncClient(_Resp(200, {"domains": []}))
    client._client = fake
    client._enabled = True
    try:
        assert asyncio.run(client.get_graph_domains()) == []
        assert fake.calls == []
        assert client.is_enabled is True
    finally:
        _cleanup()
