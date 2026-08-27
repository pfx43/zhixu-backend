"""张子麟契约修复（#29 / #34）HTTP 层测试。

依赖 PostgreSQL 测试库（conftest 自动切换到 pytest schema）。
覆盖：
- #34：GET /learning-path?goal_id= 仅校验归属，不归属/不存在抛 404，通过后返回全部文档。
- #29：tip 笔记创建/读取时锚点字段（page_number/char_start/char_end/source_ref_*）落库并透传。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from server import app
from app.api.deps import get_db, get_current_user
from app.models import Goal, User


def _create_temp_db():
    return make_sessionmaker()


def _seed_user(session, user_id: int, email: str, nickname: str = "ZlContract"):
    user = User(
        id=user_id,
        email=email,
        password_hash="hashed",
        nickname=nickname,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def client(monkeypatch):
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 9001, "email": "zl-contract@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 9001, "zl-contract@example.com", nickname="ZL")

    with TestClient(app) as test_client:
        yield test_client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


# ── #34：learning-path goal_id 归属校验 ──────────────────────

def test_learning_path_goal_id_owned_returns_ok(client):
    c, SessionLocal = client
    with SessionLocal() as db:
        db.add(Goal(user_id=9001, text="研究生上岸", status="active"))
        db.commit()
        goal_id = db.query(Goal).filter(Goal.user_id == 9001).first().id

    resp = c.get(f"/api/v1/learning-path?goal_id={goal_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert "tags" in data


def test_learning_path_goal_id_not_owned_returns_404(client):
    c, SessionLocal = client
    with SessionLocal() as db:
        db.add(Goal(user_id=9999, text="别人的目标", status="active"))
        db.commit()
        other_goal_id = db.query(Goal).filter(Goal.user_id == 9999).first().id

    resp = c.get(f"/api/v1/learning-path?goal_id={other_goal_id}")
    assert resp.status_code == 404


def test_learning_path_goal_id_missing_returns_404(client):
    c, _ = client
    resp = c.get("/api/v1/learning-path?goal_id=12345678")
    assert resp.status_code == 404


# ── #29：tip 锚点字段落库透传 ───────────────────────────────

def test_tip_note_anchor_fields_roundtrip(client):
    c, SessionLocal = client

    resp = c.post(
        "/api/v1/notes",
        json={
            "title": "易错公式",
            "content_md": "被划选的原文",
            "note_type": "tip",
            "page_number": 5,
            "char_start": 10,
            "char_end": 20,
            "source_ref_id": "session-abc",
            "source_ref_type": "tina",
        },
    )
    assert resp.status_code == 201, f"body={resp.json()}"
    data = resp.json()
    assert data["note_type"] == "tip"
    assert data["page_number"] == 5
    assert data["char_start"] == 10
    assert data["char_end"] == 20
    assert data["source_ref_id"] == "session-abc"
    assert data["source_ref_type"] == "tina"

    note_id = data["id"]
    # 读取回显同样字段
    resp2 = c.get(f"/api/v1/notes/{note_id}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["page_number"] == 5
    assert body["char_start"] == 10
    assert body["char_end"] == 20
    assert body["source_ref_id"] == "session-abc"
    assert body["source_ref_type"] == "tina"