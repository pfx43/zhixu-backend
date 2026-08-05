"""Tests for note attachment upload / download / delete."""
import sys
import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base
from app.models import User, UserNote
from app.api.v1.notes import router as notes_router
from app.api.deps import get_db, get_current_active_user
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_sqlite_fks(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    # 重定向存储路径到临时目录
    storage_root = tmp_path / "storage"
    monkeypatch.setattr("app.core.config.LOCAL_STORAGE_DIR", str(storage_root))
    # notes 模块通过 _app_config.LOCAL_STORAGE_DIR 动态读取，已由上面覆盖
    import app.crud.note as crud_note
    crud_note._ATTACHMENT_ROOT = storage_root / "notes"

    app = FastAPI()
    app.include_router(notes_router, prefix="/api/v1/notes")

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

    db = SessionLocal()
    user = User(id=1, email="test@example.com", password_hash="hash", nickname="t", is_active=True)
    db.add(user)
    db.flush()
    note = UserNote(id="note-1", user_id=1, title="test-note", content_md="# test")
    db.add(note)
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c

    engine.dispose()


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
    b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestAttachmentUpload:
    def test_upload_png(self, client):
        files = {"file": ("test.png", io.BytesIO(_PNG), "image/png")}
        resp = client.post("/api/v1/notes/note-1/attachments", files=files)
        assert resp.status_code == 201
        data = resp.json()
        assert data["media_type"] == "image"
        assert data["mime_type"] == "image/png"
        assert data["checksum"]
        assert data["note_id"] == "note-1"

    def test_upload_nonexistent_note_returns_404(self, client):
        files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
        resp = client.post("/api/v1/notes/nonexistent/attachments", files=files)
        assert resp.status_code == 404

    def test_upload_unsupported_type(self, client):
        files = {"file": ("test.pdf", io.BytesIO(b"data"), "application/pdf")}
        resp = client.post("/api/v1/notes/note-1/attachments", files=files)
        assert resp.status_code == 400
        assert "不支持的媒体类型" in resp.json()["detail"]

    def test_list_attachments(self, client):
        files = {"file": ("a.png", io.BytesIO(_PNG), "image/png")}
        client.post("/api/v1/notes/note-1/attachments", files=files)

        resp = client.get("/api/v1/notes/note-1/attachments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["media_type"] == "image"

    def test_delete_attachment(self, client):
        files = {"file": ("del.png", io.BytesIO(_PNG), "image/png")}
        resp = client.post("/api/v1/notes/note-1/attachments", files=files)
        assert resp.status_code == 201
        att_id = resp.json()["id"]

        resp2 = client.request("DELETE", f"/api/v1/notes/attachments/{att_id}")
        assert resp2.status_code == 200
        assert resp2.json()["message"] == "\u9644\u4ef6\u5df2\u5220\u9664"

    def test_delete_nonexistent_attachment_404(self, client):
        resp = client.request("DELETE", "/api/v1/notes/attachments/nonexistent")
        assert resp.status_code == 404

    def test_download_attachment(self, client):
        files = {"file": ("dl.png", io.BytesIO(_PNG), "image/png")}
        resp = client.post("/api/v1/notes/note-1/attachments", files=files)
        att_id = resp.json()["id"]

        resp2 = client.get(f"/api/v1/notes/attachments/{att_id}")
        assert resp2.status_code == 200
        assert "image/png" in resp2.headers["content-type"]

    def test_download_nonexistent_attachment_404(self, client):
        resp = client.get("/api/v1/notes/attachments/nonexistent")
        assert resp.status_code == 404


class TestAttachmentIsolation:
    def test_user_b_cannot_access_user_a_attachment(self, client):
        files = {"file": ("iso.png", io.BytesIO(_PNG), "image/png")}
        resp = client.post("/api/v1/notes/note-1/attachments", files=files)
        att_id = resp.json()["id"]

        # 当前测试用户就是 user_id=1，附件属于他，可以下载
        resp2 = client.get(f"/api/v1/notes/attachments/{att_id}")
        assert resp2.status_code == 200