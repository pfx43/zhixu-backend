import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.api.deps import get_db, get_current_user
from app.core.database import Base
from app.models import User
from app.models.onboarding import OnboardingState


def _create_temp_db():
    """Create a temp SQLite database with all ORM tables."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()
    db_url = f"sqlite:///{Path(temp_file.name).as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return temp_file.name, engine, SessionLocal


def _seed_user(session):
    user = User(
        email="onbtest@example.com",
        password_hash="hashed",
        nickname="OnboardingTest",
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def onboarding_client(monkeypatch):
    """Fixture that creates an isolated SQLite DB + user, overrides deps."""
    db_path, engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.main.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 9991, "email": "onbtest@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session)

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()
    if os.path.exists(db_path):
        os.unlink(db_path)


# ── state ──

def test_state_legacy_no_record(onboarding_client):
    """Legacy user with no onboarding record → should_show=False."""
    client, _ = onboarding_client
    resp = client.get("/api/v1/onboarding/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["should_show"] is False
    assert data["reason"] == "legacy_without_state"
    assert data["state"] is None


def test_state_in_progress(onboarding_client):
    """User with in_progress record → should_show=True."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="channel",
        ))
        db.commit()

    resp = client.get("/api/v1/onboarding/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["should_show"] is True
    assert data["reason"] == "in_progress"
    assert data["state"]["current_step"] == "channel"


# ── restart ──

def test_restart_success(onboarding_client):
    """Restart creates record and returns in_progress."""
    client, _ = onboarding_client
    resp = client.post("/api/v1/onboarding/restart", json={
        "expected_revision": 7, "mode": "all", "preserve_answers": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["current_step"] == "channel"
    assert data["steps"]["channel"] == "pending"


def test_restart_already_in_progress(onboarding_client):
    """409 when status is already in_progress."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=3,
            status="in_progress", current_step="upload",
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/restart", json={
        "expected_revision": 3, "mode": "all", "preserve_answers": True,
    })
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "onboarding_already_in_progress"
    assert detail["latest"]["status"] == "in_progress"


def test_restart_revision_conflict(onboarding_client):
    """409 when expected_revision mismatches."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=5,
            status="completed", current_step=None,
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/restart", json={
        "expected_revision": 1, "mode": "all", "preserve_answers": True,
    })
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "onboarding_revision_conflict"
    assert detail["latest"]["revision"] == 5


# ── step ──

def test_step_completed(onboarding_client):
    """Submit a completed step, advance to next pending."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="channel",
            steps={"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 1, "step": "channel", "action": "completed",
        "answer": {"channel": "friend", "channel_remark": "推荐"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["steps"]["channel"] == "completed"
    assert data["current_step"] == "upload"
    assert data["revision"] == 2


def test_step_skipped(onboarding_client):
    """Submit a skipped step, advance to next pending."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="channel",
            steps={"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 1, "step": "channel", "action": "skipped",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["steps"]["channel"] == "skipped"
    assert data["current_step"] == "upload"


def test_step_revision_conflict(onboarding_client):
    """409 when step expected_revision mismatches."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=2,
            status="in_progress", current_step="upload",
            steps={"channel": "completed", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 1, "step": "upload", "action": "completed",
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "onboarding_revision_conflict"


def test_step_auto_complete_all(onboarding_client):
    """When last step is submitted, status becomes completed."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="help",
            steps={"channel": "completed", "upload": "completed", "profile": "completed", "tags": "completed", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 1, "step": "help", "action": "completed",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["current_step"] is None


# ── complete ──

def test_complete_finalize(onboarding_client):
    """Complete when all steps are done → status=completed."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=3,
            status="in_progress", current_step=None,
            steps={"channel": "completed", "upload": "completed", "profile": "completed", "tags": "completed", "help": "completed"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/complete", json={
        "expected_revision": 3, "action": "completed",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_complete_skip_remaining(onboarding_client):
    """skip_remaining marks all pending as skipped → status=skipped."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=2,
            status="in_progress", current_step="profile",
            steps={"channel": "completed", "upload": "skipped", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/complete", json={
        "expected_revision": 2, "action": "skip_remaining",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped"
    assert data["steps"]["profile"] == "skipped"
    assert data["steps"]["tags"] == "skipped"
    assert data["steps"]["help"] == "skipped"


def test_complete_not_all_done(onboarding_client):
    """422 when action=completed but not all steps are done."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="upload",
            steps={"channel": "completed", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/complete", json={
        "expected_revision": 1, "action": "completed",
    })
    assert resp.status_code == 422


def test_complete_revision_conflict(onboarding_client):
    """409 on complete revision mismatch."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=10,
            status="in_progress", current_step=None,
            steps={"channel": "completed", "upload": "completed", "profile": "completed", "tags": "completed", "help": "completed"},
        ))
        db.commit()

    resp = client.post("/api/v1/onboarding/complete", json={
        "expected_revision": 1, "action": "completed",
    })
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "onboarding_revision_conflict"


# ── cross-request persistence (regression for state-not-persisted bug) ──

def test_step_persists_across_requests(onboarding_client):
    """POST /step then GET /state reads back the persisted revision."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="channel",
            steps={"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()

    # Step 1: submit channel step
    resp = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 1, "step": "channel", "action": "completed",
        "answer": {"channel": "friend"},
    })
    assert resp.status_code == 200, f"step channel failed: {resp.json()}"
    step_data = resp.json()
    assert step_data["revision"] == 2
    assert step_data["current_step"] == "upload"

    # Step 2: re-state via independent GET — should see persisted revision
    resp2 = client.get("/api/v1/onboarding/state")
    assert resp2.status_code == 200
    state_data = resp2.json()
    assert state_data["should_show"] is True
    assert state_data["state"]["revision"] == 2, f"expected rev 2, got {state_data['state']}"
    assert state_data["state"]["current_step"] == "upload"
    assert state_data["state"]["steps"]["channel"] == "completed"

    # Step 3: continue to upload step using revision from GET
    resp3 = client.post("/api/v1/onboarding/step", json={
        "expected_revision": 2, "step": "upload", "action": "skipped",
    })
    assert resp3.status_code == 200, f"step upload after persist failed: {resp3.json()}"
    data3 = resp3.json()
    assert data3["revision"] == 3
    assert data3["current_step"] == "profile"

    # Step 4: verify upload step persisted
    resp4 = client.get("/api/v1/onboarding/state")
    assert resp4.status_code == 200
    s4 = resp4.json()["state"]
    assert s4["revision"] == 3
    assert s4["steps"]["upload"] == "skipped"


def test_complete_persists_across_requests(onboarding_client):
    """POST /complete skip_remaining persists and read-back matches."""
    client, SessionLocal = onboarding_client
    with SessionLocal() as db:
        db.add(OnboardingState(
            user_id=9991, guide_version=1, revision=1,
            status="in_progress", current_step="channel",
            steps={"channel": "pending", "upload": "pending", "profile": "pending", "tags": "pending", "help": "pending"},
        ))
        db.commit()
    # skip_remaining from initial state
    resp = client.post("/api/v1/onboarding/complete", json={
        "expected_revision": 1, "action": "skip_remaining",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"

    # re-read
    resp2 = client.get("/api/v1/onboarding/state")
    assert resp2.status_code == 200
    s2 = resp2.json()
    assert s2["state"] is not None
    assert s2["state"]["status"] == "skipped"
    # now restart should succeed because status is skipped (not in_progress)
    resp3 = client.post("/api/v1/onboarding/restart", json={
        "expected_revision": 2, "mode": "all", "preserve_answers": False,
    })
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "in_progress"
    assert resp3.json()["current_step"] == "channel"
