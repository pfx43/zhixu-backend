from fastapi.testclient import TestClient

from server import app


REQUIRED_ONBOARDING_PATHS = [
    "/api/v1/onboarding/complete",
    "/api/v1/onboarding/restart",
    "/api/v1/onboarding/state",
    "/api/v1/onboarding/step",
]

INTERNAL_KEY_HEADER = {"X-Internal-Key": "test-internal-key"}


def test_public_health_returns_status_only():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body.keys() == {"status"}
    assert body["status"] in {"ok", "degraded"}


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
