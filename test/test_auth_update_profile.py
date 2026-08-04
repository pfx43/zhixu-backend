"""Tests for PATCH /api/v1/auth/users/me — profile update validation."""
import sys
import tempfile
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base
from app.models import User
from app.api.v1.auth import router as auth_router
from app.api.deps import get_db, get_current_active_user
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI


@pytest.fixture()
def client():
    # Use file-based SQLite so TestClient threads share the same DB
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_sqlite_fks(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")

    _test_user = {
        "user_id": 1,
        "email": "test@example.com",
        "level": 0,
    }

    def override_get_current_active_user():
        return _test_user

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_current_active_user] = override_get_current_active_user
    app.dependency_overrides[get_db] = override_get_db

    # Create a test user in the DB
    db = SessionLocal()
    user = User(
        id=1,
        email="test@example.com",
        password_hash="hash",
        nickname="tester",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    # Cleanup
    engine.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


# ── phone tests ───────────────────────────────────────────
class TestPhoneValidation:
    def test_valid_phone(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"phone": "13800138000"})
        assert resp.status_code == 200
        assert resp.json()["updated_fields"] == ["phone"]

    def test_phone_empty_string_clears(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"phone": ""})
        assert resp.status_code == 200
        assert resp.json()["updated_fields"] == ["phone"]

    def test_phone_too_short(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"phone": "12345"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any(e["loc"] == ["body", "phone"] for e in detail)

    def test_phone_non_digit(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"phone": "1380013800a"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any(e["loc"] == ["body", "phone"] for e in detail)

    def test_phone_not_start_with_1(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"phone": "29900001111"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any(e["loc"] == ["body", "phone"] for e in detail)

    def test_phone_19900001111_valid(self, client):
        """1 开头的 11 位纯数字都应接受（199 号段）"""
        resp = client.patch("/api/v1/auth/users/me", json={"phone": "19900001111"})
        assert resp.status_code == 200

    def test_phone_null_passthrough(self, client):
        """None / not-provided should be no-op (not in updated_fields)"""
        resp = client.patch("/api/v1/auth/users/me", json={"nickname": "new-name"})
        assert resp.status_code == 200
        assert "phone" not in resp.json()["updated_fields"]


# ── duplicate phone test ──────────────────────────────────
class TestDuplicatePhone:
    def test_schema_accepts_valid_phone_regression(self):
        """Schema-level guard: UpdateProfileRequest must accept valid phones."""
        from app.schemas.common import UpdateProfileRequest

        req = UpdateProfileRequest(phone="13900001111")
        assert req.phone == "13900001111"

        req2 = UpdateProfileRequest(phone="")
        assert req2.phone is None


# ── gender tests ──────────────────────────────────────────
class TestGenderValidation:
    def test_gender_male(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"gender": "男"})
        assert resp.status_code == 200
        assert resp.json()["updated_fields"] == ["gender"]

    def test_gender_female(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"gender": "女"})
        assert resp.status_code == 200

    def test_gender_empty_string_clears(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"gender": ""})
        assert resp.status_code == 200
        assert resp.json()["updated_fields"] == ["gender"]

    def test_gender_invalid_rejected(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"gender": "其他"})
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert any(e["loc"] == ["body", "gender"] for e in detail)

    def test_gender_null_passthrough(self, client):
        resp = client.patch("/api/v1/auth/users/me", json={"nickname": "new-name"})
        assert resp.status_code == 200
        assert "gender" not in resp.json()["updated_fields"]


# ── 422 loc stability ─────────────────────────────────────
class Test422FieldLoc:
    def test_phone_and_gender_both_invalid(self, client):
        """Both fields invalid → two entries in detail, loc points correctly"""
        resp = client.patch(
            "/api/v1/auth/users/me",
            json={"phone": "abc", "gender": "未知"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        locs = {tuple(e["loc"]) for e in detail}
        assert ("body", "phone") in locs
        assert ("body", "gender") in locs