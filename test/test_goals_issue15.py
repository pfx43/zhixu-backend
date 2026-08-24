"""Issue #15 Goal — HTTP 测试覆盖

验收条件：
1. 登录用户写入目标后，刷新 GET /goals 仍能读到同一条 active。
2. 另一用户的 token 读不到这条。
3. 同时 PUT 第二条 active 时，仍只有一条 active（更新现有那条，不会新建第二条）。
4. 删号后该用户 goals 行为空。
5. 引导可在无完整老五步的情况下结束并带上 nickname + goal。
6. 无「勾选我学会了」接口。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from server import app
from app.api.deps import get_db, get_current_user
from app.models import User, Goal


def _create_temp_db():
    return make_sessionmaker()


def _seed_user(session, user_id: int, email: str, nickname: str = "GoalTest"):
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
def goals_client(monkeypatch):
    """主用户（id=8801）"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 8801, "email": "goal-a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "goal-a@example.com", nickname="Alice")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture()
def goals_client_other(monkeypatch):
    """另一用户（id=8802），用于验证隔离"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 8802, "email": "goal-b@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "goal-a@example.com", nickname="Alice")
        _seed_user(session, 8802, "goal-b@example.com", nickname="Bob")
        # 主用户先写一条 goal，然后我们用另一个用户客户端读
        session.add(Goal(
            user_id=8801,
            text="研究生上岸",
            status="active",
            attributes={"subject": "计算机"},
        ))
        session.commit()

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


# ── 验收 1：写入后刷新可读 ──────────────────────────────────────

def test_upsert_active_goal_and_read_back(goals_client):
    client, SessionLocal = goals_client

    # 初始为空
    resp = client.get("/api/v1/goals")
    assert resp.status_code == 200
    assert resp.json() == []

    # 写入第一条 active
    resp = client.put("/api/v1/goals/active", json={
        "text": "研究生上岸",
        "attributes": {"subject": "计算机", "target_book": "数据结构"},
    })
    assert resp.status_code == 200
    data = resp.json()
    goal_id = data["id"]
    assert data["text"] == "研究生上岸"
    assert data["status"] == "active"
    assert data["attributes"] == {"subject": "计算机", "target_book": "数据结构"}

    # 刷新 GET 仍能读到同一条
    resp2 = client.get("/api/v1/goals")
    assert resp2.status_code == 200
    goals = resp2.json()
    assert len(goals) == 1
    assert goals[0]["id"] == goal_id
    assert goals[0]["status"] == "active"
    assert goals[0]["text"] == "研究生上岸"


# ── 验收 2：另一用户读不到 ──────────────────────────────────────

def test_goals_isolated_between_users(goals_client_other):
    client, _ = goals_client_other

    # 8802 用户拿自己的列表，看不到 8801 的
    resp = client.get("/api/v1/goals")
    assert resp.status_code == 200
    assert resp.json() == []


# ── 验收 3：第二次 PUT 是更新，不是新建第二条 active ─────────

def test_second_put_active_updates_existing_no_duplicate(goals_client):
    client, SessionLocal = goals_client

    # 第一次
    r1 = client.put("/api/v1/goals/active", json={"text": "目标 A"})
    assert r1.status_code == 200
    id_first = r1.json()["id"]
    assert r1.json()["text"] == "目标 A"

    # 第二次 PUT active → 应该更新同一条，而不是新建
    r2 = client.put("/api/v1/goals/active", json={
        "text": "目标 B",
        "attributes": {"updated": True},
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == id_first
    assert r2.json()["text"] == "目标 B"
    assert r2.json()["status"] == "active"

    # 数据库里只有这一条，且只有一条 active
    with SessionLocal() as db:
        all_rows = db.query(Goal).filter(Goal.user_id == 8801).all()
        active_rows = [g for g in all_rows if g.status == "active"]
        assert len(all_rows) == 1
        assert len(active_rows) == 1
        assert all_rows[0].text == "目标 B"


# ── 验收 4：删号后 goals 清空 ──────────────────────────────────

def test_delete_account_clears_goals(goals_client, monkeypatch):
    from app.services.auth import auth_service
    from app.services.auth.auth_service import AuthManager

    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    client, SessionLocal = goals_client

    # 先写 2 条历史 goal + 1 条 active
    with SessionLocal() as db:
        db.add_all([
            Goal(user_id=8801, text="旧目标 paused", status="paused"),
            Goal(user_id=8801, text="旧目标 completed", status="completed"),
        ])
        db.commit()

    client.put("/api/v1/goals/active", json={"text": "进行中目标"})

    with SessionLocal() as db:
        assert db.query(Goal).filter(Goal.user_id == 8801).count() == 3
        # 调用删号
        AuthManager.delete_account(db, 8801)
        assert db.query(Goal).filter(Goal.user_id == 8801).count() == 0


# ── 验收 5：引导跳过老五步，写入 nickname + goal ────────────────

def test_onboarding_skip_remaining_writes_nickname_and_goal(goals_client):
    client, SessionLocal = goals_client

    resp = client.post("/api/v1/onboarding/finish-with-goal", json={
        "nickname": "小王",
        "goal_text": "考研上岸 408",
        "goal_attributes": {"subject": "计算机统考"},
        "expected_revision": 0,
        "action": "skip_remaining",
    })
    assert resp.status_code == 200, f"body={resp.json()}"
    data = resp.json()

    assert data["profile"]["nickname"] == "小王"
    assert data["profile"]["user_id"] == 8801
    assert data["goal"]["text"] == "考研上岸 408"
    assert data["goal"]["status"] == "active"
    assert data["goal"]["attributes"] == {"subject": "计算机统考"}
    assert data["onboarding"]["status"] in ("skipped", "completed")

    # 用户 nickname 真的改了
    with SessionLocal() as db:
        u = db.query(User).filter(User.id == 8801).first()
        assert u.nickname == "小王"

        g = db.query(Goal).filter(Goal.user_id == 8801, Goal.status == "active").first()
        assert g is not None
        assert g.text == "考研上岸 408"

    # GET /goals 和 /me/profile 也一致
    r_goals = client.get("/api/v1/goals")
    assert r_goals.status_code == 200
    assert len(r_goals.json()) >= 1
    assert r_goals.json()[0]["text"] == "考研上岸 408"

    r_profile = client.get("/api/v1/me/profile")
    assert r_profile.status_code == 200
    assert r_profile.json()["nickname"] == "小王"


# ── Profile 接口自测 ────────────────────────────────────────────

def test_profile_put_and_get(goals_client):
    client, _ = goals_client

    # GET 初始
    r = client.get("/api/v1/me/profile")
    assert r.status_code == 200
    assert r.json()["nickname"] == "Alice"
    assert r.json()["user_id"] == 8801

    # PUT 更新
    r2 = client.put("/api/v1/me/profile", json={"nickname": "新称呼"})
    assert r2.status_code == 200
    assert r2.json()["nickname"] == "新称呼"

    # 再 GET 验证刷新可读
    r3 = client.get("/api/v1/me/profile")
    assert r3.status_code == 200
    assert r3.json()["nickname"] == "新称呼"


# ── 验收 6：不暴露「勾选我学会了」completed 接口 ───────────────

def test_no_complete_goal_endpoint_exposed(goals_client):
    """用户不能手点完成目标。只有 /goals/active（upsert），没有 PATCH /goals/{id}/status。"""
    client, _ = goals_client

    # 不存在的路由应该 404 / 405
    r = client.patch("/api/v1/goals/999/status", json={"status": "completed"})
    assert r.status_code in (404, 405)

    r = client.post("/api/v1/goals/complete", json={"goal_id": 1})
    assert r.status_code in (404, 405)
