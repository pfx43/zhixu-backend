import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.v1 import kt as kt_router_module
from app.api.v1.router import api_router
from app.services.tcn.tcn_client import tcn_client


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(kt_router_module.router, prefix="/kt")

    class DummyUser(dict):
        pass

    def fake_current_user():
        return DummyUser(user_hash="demo-user", is_active=True)

    app.dependency_overrides[kt_router_module.get_current_active_user] = fake_current_user

    async def fake_summary(user_hash):
        return {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "total_steps": 1,
            "overall_mastery": 0.8,
            "global_lvr": 0.01,
            "lvr_level": "normal",
            "graph_version": 1,
            "domain_summary": [],
            "last_active_node": None,
            "computed_at": None,
        }

    async def fake_gaps(user_hash, limit=50, threshold=0.6):
        return {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "mastery_threshold": threshold,
            "total_gaps": 1,
            "returned_gaps": 1,
            "limit": limit,
            "gaps": [],
            "computed_at": None,
        }

    async def fake_vulnerabilities(user_hash, limit=50):
        return {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "mastery_threshold_high": 0.7,
            "total_vulnerabilities": 0,
            "returned_vulnerabilities": 0,
            "limit": limit,
            "vulnerabilities": [],
            "computed_at": None,
        }

    async def fake_lvr_alert(user_hash, limit=10):
        return {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "global_lvr": 0.0,
            "lvr_level": "normal",
            "alert_code": "LVR_NORMAL",
            "alert_text": None,
            "total_violations": 0,
            "returned_violations": 0,
            "limit": limit,
            "violations": [],
            "backtrack_recommended": [],
            "computed_at": None,
        }

    monkeypatch.setattr(tcn_client, "get_summary", fake_summary)
    monkeypatch.setattr(tcn_client, "get_gaps", fake_gaps)
    monkeypatch.setattr(tcn_client, "get_vulnerabilities", fake_vulnerabilities)
    monkeypatch.setattr(tcn_client, "get_lvr_alert", fake_lvr_alert)

    return TestClient(app)


def test_summary_endpoint_returns_documented_payload(client):
    response = client.get("/kt/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["user_hash"] == "demo-user"
    assert body["diagnosis_version"] == "rule"
    assert body["overall_mastery"] == 0.8


def test_gaps_endpoint_enforces_query_limits(client):
    response = client.get("/kt/gaps", params={"limit": 201})
    assert response.status_code == 422


def test_vulnerabilities_endpoint_returns_documented_payload(client):
    response = client.get("/kt/vulnerabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["mastery_threshold_high"] == 0.7


def test_lvr_alert_endpoint_returns_documented_payload(client):
    response = client.get("/kt/lvr-alert")
    assert response.status_code == 200
    body = response.json()
    assert body["alert_code"] == "LVR_NORMAL"
