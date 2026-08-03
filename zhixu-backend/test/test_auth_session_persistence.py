import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.deps import get_db
from app.core.database import Base
from app.core.redis import cache
from app.models import AuthSession, User
from app.services.auth import auth_service
from app.services.auth.auth_session_service import create_auth_session, hash_token
from server import app


@pytest.fixture()
def auth_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with testing_session() as db:
        db.add(
            User(
                email="restart-session@example.com",
                password_hash="hash",
                nickname="restart-session",
                is_active=True,
            )
        )
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(auth_service, "verify_password", lambda _plain, _hashed: True)
    monkeypatch.setattr(auth_service, "get_password_hash", lambda _password: "new-hash")
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), testing_session
    finally:
        app.dependency_overrides.clear()
        for key in list(cache.scan_keys("auth:token:*")):
            cache.delete_key(key)
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_login_session_survives_process_cache_reset(auth_client):
    client, _testing_session = auth_client
    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    cache.delete_key(f"auth:token:{token}")

    current_user_response = client.get(
        "/api/v1/auth/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert current_user_response.status_code == 200
    assert current_user_response.json()["email"] == "restart-session@example.com"


def test_login_persists_only_token_hash(auth_client):
    client, testing_session = auth_client
    token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]

    with testing_session() as db:
        persisted_session = db.query(AuthSession).one()

    assert persisted_session.token_hash == hash_token(token)
    assert persisted_session.token_hash != token


def test_login_removes_expired_sessions(auth_client):
    client, testing_session = auth_client
    expired_token = "expired-session-token"
    with testing_session() as db:
        user = db.query(User).one()
        create_auth_session(
            db,
            token=expired_token,
            user_id=user.id,
            ttl_seconds=-1,
        )
        db.commit()

    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )

    assert login_response.status_code == 200
    with testing_session() as db:
        assert db.query(AuthSession).filter(
            AuthSession.token_hash == hash_token(expired_token)
        ).count() == 0


def test_token_debug_endpoint_uses_persisted_session(auth_client):
    client, _testing_session = auth_client
    token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]
    cache.delete_key(f"auth:token:{token}")

    response = client.get(
        "/api/v1/auth/test-token-info",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["your_user_id"] == 1


def test_refresh_rotates_persisted_session_after_process_cache_reset(auth_client):
    client, _testing_session = auth_client
    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )
    old_token = login_response.json()["access_token"]
    cache.delete_key(f"auth:token:{old_token}")

    refresh_response = client.post(
        "/api/v1/auth/refresh-token",
        json={"refresh_token": old_token},
    )

    assert refresh_response.status_code == 200
    new_token = refresh_response.json()["access_token"]
    assert new_token != old_token
    assert client.get(
        "/api/v1/auth/users/me",
        headers={"Authorization": f"Bearer {old_token}"},
    ).status_code == 401
    assert client.get(
        "/api/v1/auth/users/me",
        headers={"Authorization": f"Bearer {new_token}"},
    ).status_code == 200


def test_concurrent_refresh_issues_only_one_new_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'concurrent-refresh.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    old_token = "concurrent-refresh-token"
    with testing_session() as db:
        user = User(
            email="concurrent-refresh@example.com",
            password_hash="hash",
            nickname="concurrent-refresh",
            is_active=True,
        )
        db.add(user)
        db.flush()
        create_auth_session(db, token=old_token, user_id=user.id, ttl_seconds=300)
        db.commit()

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        def refresh():
            return TestClient(app).post(
                "/api/v1/auth/refresh-token",
                json={"refresh_token": old_token},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _index: refresh(), range(2)))

        assert sorted(response.status_code for response in responses) == [200, 401]
        new_token = next(
            response.json()["access_token"]
            for response in responses
            if response.status_code == 200
        )
        client = TestClient(app)
        assert client.get(
            "/api/v1/auth/users/me",
            headers={"Authorization": f"Bearer {old_token}"},
        ).status_code == 401
        assert client.get(
            "/api/v1/auth/users/me",
            headers={"Authorization": f"Bearer {new_token}"},
        ).status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_logout_revokes_persisted_session(auth_client):
    client, _testing_session = auth_client
    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )
    token = login_response.json()["access_token"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert logout_response.status_code == 200
    assert client.get(
        "/api/v1/auth/users/me",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401


def test_change_password_revokes_all_persisted_sessions(auth_client):
    client, _testing_session = auth_client
    first_token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]
    second_token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]

    change_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {first_token}"},
        json={"old_password": "secret", "new_password": "new-secret"},
    )

    assert change_response.status_code == 200
    for token in (first_token, second_token):
        assert client.get(
            "/api/v1/auth/users/me",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 401


def test_reset_password_revokes_all_persisted_sessions(auth_client, monkeypatch):
    client, _testing_session = auth_client
    first_token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]
    second_token = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    ).json()["access_token"]
    reset_token = "persisted-session-reset-token"
    cache.set_value(
        f"password_reset:{reset_token}",
        "restart-session@example.com",
        ttl=300,
    )
    monkeypatch.setattr(
        auth_service,
        "verify_password",
        lambda plain, _hashed: plain != "new-secret",
    )

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={"reset_token": reset_token, "new_password": "new-secret"},
    )

    assert reset_response.status_code == 200
    for token in (first_token, second_token):
        assert client.get(
            "/api/v1/auth/users/me",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 401


def test_delete_account_revokes_session_and_prevents_relogin(auth_client):
    client, _testing_session = auth_client
    login_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    delete_response = client.delete("/api/v1/auth/account", headers=headers)

    assert delete_response.status_code == 200
    assert client.get("/api/v1/auth/users/me", headers=headers).status_code == 401
    relogin_response = client.post(
        "/api/v1/auth/token",
        data={"username": "restart-session@example.com", "password": "secret"},
    )
    assert relogin_response.status_code == 404
