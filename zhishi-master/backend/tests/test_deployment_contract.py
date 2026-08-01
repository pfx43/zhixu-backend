from fastapi.testclient import TestClient

from server import app


REQUIRED_ONBOARDING_PATHS = [
    "/api/v1/onboarding/complete",
    "/api/v1/onboarding/restart",
    "/api/v1/onboarding/state",
    "/api/v1/onboarding/step",
]


def test_health_reports_complete_onboarding_api_contract():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    contract = response.json()["api_contract"]
    assert contract == {
        "status": "ok",
        "required_paths": REQUIRED_ONBOARDING_PATHS,
        "missing_paths": [],
    }
