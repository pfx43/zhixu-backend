from fastapi.testclient import TestClient

from server import app


REQUIRED_ONBOARDING_PATHS = [
    "/api/v1/onboarding/complete",
    "/api/v1/onboarding/restart",
    "/api/v1/onboarding/state",
    "/api/v1/onboarding/step",
]

INTERNAL_KEY_HEADER = {"X-Internal-Key": "test-internal-key"}


def test_public_health_returns_full_contract():
    # #33：/health 返回完整契约（含 api_contract.missing_paths），顶层保留 status。
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert "api_contract" in body
    assert body["api_contract"]["required_paths"] == REQUIRED_ONBOARDING_PATHS
    assert body["api_contract"]["missing_paths"] == []


def test_openapi_json_available():
    # #32：openapi.json 恢复可读（docs/redoc 仍关闭）。
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()


def test_health_detailed_reports_complete_onboarding_api_contract():
    response = TestClient(app).get("/health/detailed", headers=INTERNAL_KEY_HEADER)

    assert response.status_code == 200
    contract = response.json()["api_contract"]
    assert contract == {
        "status": "ok",
        "required_paths": REQUIRED_ONBOARDING_PATHS,
        "missing_paths": [],
    }


def test_health_detailed_rejects_missing_or_wrong_key():
    client = TestClient(app)

    assert client.get("/health/detailed").status_code == 403
    assert (
        client.get(
            "/health/detailed", headers={"X-Internal-Key": "wrong-key"}
        ).status_code
        == 403
    )
