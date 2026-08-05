"""Tests for note soft-delete / restore / trash listing."""
import sys
import tempfile
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base
from app.models import User
from app.crud import note as note_crud
from app.api.v1.notes import router as notes_router
from app.api.deps import get_db, get_current_active_user
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI


@pytest.fixture()
def client():
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

    engine.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


class TestNoteSoftDelete:
    def test_create_and_soft_delete(self, client):
        resp = client.post("/api/v1/notes", json={"title": "test-note", "content_md": "# hello"})
        assert resp.status_code == 201
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        resp2 = client.get("/api/v1/notes")
        assert resp2.status_code == 200
        ids = [n["id"] for n in resp2.json()]
        assert note_id in ids

        resp3 = client.request("DELETE", f"/api/v1/notes/{note_id}", json={"expected_revision": rev})
        assert resp3.status_code == 200
        assert resp3.json()["message"] == "\u7b14\u8bb0\u5df2\u79fb\u5165\u56de\u6536\u7ad9"
        new_rev = resp3.json()["revision"]
        assert new_rev == rev + 1

        resp4 = client.get("/api/v1/notes")
        ids2 = [n["id"] for n in resp4.json()]
        assert note_id not in ids2

    def test_soft_delete_then_restore(self, client):
        resp = client.post("/api/v1/notes", json={"title": "restore-me", "content_md": "# t"})
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        resp2 = client.request("DELETE", f"/api/v1/notes/{note_id}", json={"expected_revision": rev})
        assert resp2.status_code == 200
        trash_rev = resp2.json()["revision"]

        resp3 = client.get("/api/v1/notes/trash/items")
        assert resp3.status_code == 200
        trash_ids = [n["id"] for n in resp3.json()]
        assert note_id in trash_ids

        resp4 = client.post(
            f"/api/v1/notes/{note_id}/restore",
            json={"expected_revision": trash_rev},
        )
        assert resp4.status_code == 200
        restored_rev = resp4.json()["revision"]
        assert restored_rev == trash_rev + 1

        resp5 = client.get("/api/v1/notes")
        ids = [n["id"] for n in resp5.json()]
        assert note_id in ids

        resp6 = client.get("/api/v1/notes/trash/items")
        trash_ids2 = [n["id"] for n in resp6.json()]
        assert note_id not in trash_ids2

    def test_delete_nonexistent_note_returns_404(self, client):
        resp = client.request("DELETE", "/api/v1/notes/nonexistent-id", json={"expected_revision": 1})
        assert resp.status_code == 404

    def test_delete_revision_conflict(self, client):
        resp = client.post("/api/v1/notes", json={"title": "conflict-delete", "content_md": "# c"})
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        client.patch(
            f"/api/v1/notes/{note_id}",
            json={"expected_revision": rev, "title": "conflict-delete-updated"},
        )

        resp2 = client.request("DELETE", f"/api/v1/notes/{note_id}", json={"expected_revision": rev})
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["code"] == "note_revision_conflict"

    def test_restore_revision_conflict(self, client):
        resp = client.post("/api/v1/notes", json={"title": "conflict-restore", "content_md": "# r"})
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        client.request("DELETE", f"/api/v1/notes/{note_id}", json={"expected_revision": rev})

        resp2 = client.post(
            f"/api/v1/notes/{note_id}/restore",
            json={"expected_revision": 1},
        )
        assert resp2.status_code == 409

    def test_restore_not_deleted_note_is_idempotent(self, client):
        resp = client.post("/api/v1/notes", json={"title": "not-deleted", "content_md": "# nd"})
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        resp2 = client.post(
            f"/api/v1/notes/{note_id}/restore",
            json={"expected_revision": rev},
        )
        assert resp2.status_code == 200

    def test_trash_empty(self, client):
        resp = client.get("/api/v1/notes/trash/items")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCrossUserIsolation:
    def test_user_b_cannot_see_user_a_trash(self, client):
        resp = client.post("/api/v1/notes", json={"title": "user-a-note", "content_md": "# a"})
        note_id = resp.json()["id"]
        rev = resp.json()["revision"]

        client.request("DELETE", f"/api/v1/notes/{note_id}", json={"expected_revision": rev})

        resp2 = client.get("/api/v1/notes/trash/items")
        trash_ids = [n["id"] for n in resp2.json()]
        assert note_id in trash_ids


class TestPurgeExpired:
    def test_purge_expired_notes(self, client):
        import os
        from app.crud.note import purge_expired_notes
        from app.models import UserNote
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from datetime import datetime, timezone, timedelta

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        user = User(id=99, email="purge@test.com", password_hash="h", nickname="p", is_active=True)
        db.add(user)
        db.flush()

        recent = UserNote(
            id="note-recent", user_id=99, title="recent", content_md="#r",
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            deleted_by_revision=1,
            revision=2,
        )
        db.add(recent)

        old = UserNote(
            id="note-old", user_id=99, title="old", content_md="#o",
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=8),
            deleted_by_revision=1,
            revision=2,
        )
        db.add(old)

        active = UserNote(
            id="note-active", user_id=99, title="active", content_md="#a",
        )
        db.add(active)

        db.commit()

        count = purge_expired_notes(db)
        db.commit()

        assert count == 1
        assert db.query(UserNote).filter(UserNote.id == "note-active").first() is not None
        assert db.query(UserNote).filter(UserNote.id == "note-recent").first() is not None
        assert db.query(UserNote).filter(UserNote.id == "note-old").first() is None

        db.close()
        engine.dispose()
        os.unlink(db_path)