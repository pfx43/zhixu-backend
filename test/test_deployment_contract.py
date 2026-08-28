from fastapi.testclient import TestClient

from server import app, REQUIRED_DEPLOYMENT_PATHS

INTERNAL_KEY_HEADER = {"X-Internal-Key": "test-internal-key"}


def _available_paths() -> set[str]:
    """公开 OpenAPI 中的实际路径集合（与 health 内部使用的同一份）。"""
    return set(app.openapi().get("paths", {}))


def _expected_missing_paths() -> list[str]:
    available = _available_paths()
    return [p for p in REQUIRED_DEPLOYMENT_PATHS if p not in available]


def test_public_health_returns_full_contract():
    # #33：/health 返回完整契约（含 api_contract.missing_paths），顶层保留 status。
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "api_contract" in body

    contract = body["api_contract"]
    # 名单与 server 单一数据源一致，不复制第二份。
    assert contract["required_paths"] == list(REQUIRED_DEPLOYMENT_PATHS)
    # missing_paths 与公开 openapi 动态对账。
    assert contract["missing_paths"] == _expected_missing_paths()
    # status 必须诚实反映是否缺路径。
    assert contract["status"] == ("ok" if not contract["missing_paths"] else "invalid")


def test_health_contract_flags_unmounted_notifications():
    # #33 守卫：通知路由未挂时，/api/v1/notifications 必须出现在 missing_paths。
    # #43 合入后该路径可读，此守卫自动失效（不再断言 missing，只断言契约一致性）。
    available = _available_paths()
    if "/api/v1/notifications" not in available:
        response = TestClient(app).get("/health")
        contract = response.json()["api_contract"]
        assert "/api/v1/notifications" in contract["missing_paths"]
        assert contract["status"] == "invalid"


def test_openapi_json_available():
    # #32：openapi.json 恢复可读（docs/redoc 仍关闭）。
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()


def test_health_detailed_reports_full_contract():
    response = TestClient(app).get("/health/detailed", headers=INTERNAL_KEY_HEADER)

    assert response.status_code == 200
    contract = response.json()["api_contract"]
    assert contract["required_paths"] == list(REQUIRED_DEPLOYMENT_PATHS)
    assert contract["missing_paths"] == _expected_missing_paths()
    assert contract["status"] == ("ok" if not contract["missing_paths"] else "invalid")


def test_health_detailed_rejects_missing_or_wrong_key():
    client = TestClient(app)

    assert client.get("/health/detailed").status_code == 403
    assert (
        client.get(
            "/health/detailed", headers={"X-Internal-Key": "wrong-key"}
        ).status_code
        == 403
    )