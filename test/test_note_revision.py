from __future__ import annotations

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_active_user, get_db
from app.core.database import Base
from server import app
from app.models import User


def _create_temp_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def notes_client(monkeypatch):
    """在隔离 SQLite 数据库上暴露 Notes HTTP 契约。"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    with SessionLocal() as db:
        first_user = User(
            email="notes-first@example.com",
            password_hash="hash",
            nickname="Notes First",
            is_active=True,
        )
        second_user = User(
            email="notes-second@example.com",
            password_hash="hash",
            nickname="Notes Second",
            is_active=True,
        )
        db.add_all([first_user, second_user])
        db.commit()
        db.refresh(first_user)
        db.refresh(second_user)
        users = {"first": first_user.id, "second": second_user.id}

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    tokens = {
        "Bearer notes-first-token": users["first"],
        "Bearer notes-second-token": users["second"],
    }

    def override_current_active_user(
        authorization: str | None = Header(default=None),
    ):
        user_id = tokens.get(authorization)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return {"user_id": user_id, "is_active": True}

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_active_user] = override_current_active_user

    try:
        with TestClient(app) as client:
            yield client, SessionLocal, users
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _auth(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer notes-{user}-token"}


def test_note_create_detail_and_list_return_initial_revision(notes_client):
    """客户端可从每条读路径建立同一个稳定 revision 基线。"""
    client, _SessionLocal, _users = notes_client

    create_response = client.post(
        "/api/v1/notes",
        json={"title": "版本化笔记", "content_md": "初始内容"},
        headers=_auth("first"),
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["revision"] == 1

    detail_response = client.get(
        f"/api/v1/notes/{created['id']}",
        headers=_auth("first"),
    )
    list_response = client.get("/api/v1/notes", headers=_auth("first"))

    assert detail_response.status_code == 200
    assert detail_response.json()["revision"] == 1
    assert list_response.status_code == 200
    assert list_response.json()[0]["revision"] == 1


def test_note_update_requires_base_revision_and_returns_the_next_revision(notes_client):
    """一次被接受的写入恰好推进一次稳定令牌。"""
    client, _SessionLocal, _users = notes_client
    created = client.post(
        "/api/v1/notes",
        json={"title": "待更新", "content_md": "旧内容"},
        headers=_auth("first"),
    ).json()

    missing_base_response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"content_md": "不应写入"},
        headers=_auth("first"),
    )
    update_response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"expected_revision": 1, "content_md": "新内容"},
        headers=_auth("first"),
    )

    assert missing_base_response.status_code == 422
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["content_md"] == "新内容"
    assert updated["revision"] == 2


def test_stale_note_update_returns_only_conflict_metadata(notes_client):
    """陈旧离线 outbox 操作不会收到更新后的笔记内容。"""
    client, _SessionLocal, _users = notes_client
    created = client.post(
        "/api/v1/notes",
        json={"title": "冲突笔记", "content_md": "私密旧内容"},
        headers=_auth("first"),
    ).json()

    winning_response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"expected_revision": 1, "content_md": "已保存的新内容"},
        headers=_auth("first"),
    )
    stale_response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"expected_revision": 1, "content_md": "陈旧离线内容"},
        headers=_auth("first"),
    )

    assert winning_response.status_code == 200
    assert stale_response.status_code == 409
    assert stale_response.json() == {
        "detail": {
            "code": "note_revision_conflict",
            "detail": "笔记已被更新，请使用最新版本重试",
            "current_revision": 2,
        }
    }


def test_other_user_cannot_probe_a_note_revision(notes_client):
    """非属主只能得到普通 404，绝不能拿到 409 版本元数据。"""
    client, _SessionLocal, _users = notes_client
    created = client.post(
        "/api/v1/notes",
        json={"title": "仅本人可见", "content_md": "私密内容"},
        headers=_auth("first"),
    ).json()

    response = client.patch(
        f"/api/v1/notes/{created['id']}",
        json={"expected_revision": 1, "content_md": "越权更新"},
        headers=_auth("second"),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "笔记不存在"}


def test_notes_openapi_publishes_revision_update_and_conflict_contract(notes_client):
    """生成的 OpenAPI 必须暴露精确的移动端 outbox 契约。"""
    client, _SessionLocal, _users = notes_client
    openapi = client.get("/openapi.json").json()
    components = openapi["components"]["schemas"]

    update_schema = components["NoteUpdate"]
    assert "expected_revision" in update_schema["required"]
    assert update_schema["properties"]["expected_revision"]["minimum"] == 1
    assert components["NoteResponse"]["properties"]["revision"]["type"] == "integer"

    patch_responses = openapi["paths"]["/api/v1/notes/{note_id}"]["patch"][
        "responses"
    ]
    conflict_schema = patch_responses["409"]["content"]["application/json"][
        "schema"
    ]
    conflict_name = conflict_schema["$ref"].rsplit("/", 1)[-1]
    assert conflict_name == "NoteRevisionConflictResponse"
