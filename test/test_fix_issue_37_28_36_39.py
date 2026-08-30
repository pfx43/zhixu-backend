"""Issue #28 / #36 / #37 / #39 修复测试。

- #28：通知/提醒/画像路由已挂载，空账号 200/201（不再 404）
- #37：画像推断执行器 — POST /profile/inferences 后任务最终 done，graph.nodes 非空
- #36：提醒到期 worker — 到期写 notifications、状态流转、repeat 推进、disabled/未来不触发
- #39：tip 回源契约 — tina_message 必须带 source_session_id；quiz_session/tutor 校验归属
"""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from server import app
from app.api.deps import get_db, get_current_user
from app.models import (
    Document,
    Goal,
    KbCollection,
    Notification,
    ProfileInference,
    QuizSession,
    Reminder,
    User,
    UserNote,
)
from app.services.notifications.reminder_worker import (
    compute_next_trigger_at,
    process_due_reminders,
)
from app.services.profile.inference_service import build_profile_graph

CONTRACT_PATHS = (
    "/api/v1/notifications",
    "/api/v1/notifications/unread-count",
    "/api/v1/reminders",
    "/api/v1/profile/graph",
    "/api/v1/profile/inferences",
    "/api/v1/profile/inferences/{inference_id}",
)


def _seed_user(session, user_id, email, nickname="U"):
    session.add(User(id=user_id, email=email, password_hash="h", nickname=nickname, is_active=True))
    session.commit()


def _seed_document(session, user_id, doc_id, name="书.pdf"):
    coll = KbCollection(id=f"coll-{doc_id}", user_id=user_id, name="学习区", zone="study", is_default=True)
    session.add(coll)
    session.flush()
    doc = Document(
        id=doc_id, user_id=user_id, collection_id=coll.id, display_name=name, zone="study",
        content_hash=f"hash-{doc_id}", parsed_cache_key=f"parsed-{doc_id}",
        indexing_status="completed", segment_status="completed", question_gen_status="completed",
    )
    session.add(doc)
    session.commit()
    return doc


def _seed_goal(session, user_id, text="研究生上岸"):
    g = Goal(user_id=user_id, text=text, status="active")
    session.add(g)
    session.commit()
    return g


@pytest.fixture()
def client(monkeypatch):
    """主用户（id=8801），关掉提醒 worker 避免测试相互干扰。"""
    monkeypatch.setenv("REMINDER_WORKER_ENABLED", "false")
    engine, SessionLocal = make_sessionmaker()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    def override_get_current_user():
        return {"user_id": 8801, "email": "a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com")
        _seed_document(s, 8801, "doc-a")
        _seed_goal(s, 8801)
    with TestClient(app) as c:
        yield c, SessionLocal
    engine.dispose()
    app.dependency_overrides.clear()


# ── #28 路由挂载 ────────────────────────────────────────────

def test_28_contract_paths_in_openapi(client):
    c, _ = client
    paths = app.openapi().get("paths", {})
    for p in CONTRACT_PATHS:
        assert p in paths, f"契约路径缺失: {p}"


def test_28_notification_reminder_profile_not_404(client, monkeypatch):
    monkeypatch.setenv("PROFILE_INFERENCE_MODE", "sync")
    c, SessionLocal = client
    assert c.get("/api/v1/notifications").status_code == 200
    assert c.get("/api/v1/notifications/unread-count").json() == {"unread": 0}
    assert c.get("/api/v1/reminders").status_code == 200
    r = c.post("/api/v1/reminders", json={"title": "复习", "trigger_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    assert r.status_code == 201
    assert c.get("/api/v1/profile/graph").status_code == 200
    assert c.post("/api/v1/profile/inferences").status_code == 201


# ── #37 画像执行器 ──────────────────────────────────────────

def test_37_inference_sync_completes_with_graph(client, monkeypatch):
    monkeypatch.setenv("PROFILE_INFERENCE_MODE", "sync")
    c, SessionLocal = client
    # 给用户一点 tip 数据，让图有标签节点
    with SessionLocal() as s:
        s.add(UserNote(id="tip-1", user_id=8801, title="难词", content_md="abc", note_type="tip",
                       tags=["英语难词"], source="tina", document_id="doc-a"))
        s.commit()

    r = c.post("/api/v1/profile/inferences")
    assert r.status_code == 201
    inf_id = r.json()["id"]
    r2 = c.get(f"/api/v1/profile/inferences/{inf_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "done", f"同步执行应直接 done，实际 {body['status']}: {body.get('error')}"
    assert body.get("result", {}).get("node_count", 0) > 0

    graph = c.get("/api/v1/profile/graph").json()
    nodes = (graph.get("graph") or {}).get("nodes") or []
    assert len(nodes) > 0, "done 后 graph 的 nodes 不应为空"
    node_types = {n["node_type"] for n in nodes}
    assert "user" in node_types and "goal" in node_types


def test_37_inference_async_polls_to_done(client):
    """异步模式：任务从 running 轮询到 done，绝不永久 running。"""
    c, SessionLocal = client
    r = c.post("/api/v1/profile/inferences")
    assert r.status_code == 201
    inf_id = r.json()["id"]
    deadline = time.time() + 15
    status = r.json()["status"]
    while status in ("running", "pending") and time.time() < deadline:
        time.sleep(0.2)
        status = c.get(f"/api/v1/profile/inferences/{inf_id}").json()["status"]
    assert status in ("done", "failed"), f"约定窗口内未收敛，仍为 {status}"
    if status == "failed":
        assert c.get(f"/api/v1/profile/inferences/{inf_id}").json().get("error")
    else:
        graph = c.get("/api/v1/profile/graph").json()
        assert len((graph.get("graph") or {}).get("nodes") or []) > 0


def test_37_build_graph_empty_user_has_user_node():
    """空账号（无资料/目标/tip）构建的图至少包含 user 节点。"""
    engine, SessionLocal = make_sessionmaker()
    with SessionLocal() as s:
        _seed_user(s, 9901, "empty@example.com")
        g = build_profile_graph(s, 9901)
    engine.dispose()
    assert g["nodes"], "空账号至少应有 user 节点"
    assert g["nodes"][0]["node_type"] == "user"


# ── #36 提醒到期 worker ─────────────────────────────────────

def test_36_due_reminder_fires_notification_and_status(client):
    c, SessionLocal = client
    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        s.add(Reminder(id="rem-1", user_id=8801, title="到期提醒", body="该复习了",
                       trigger_at=now - timedelta(minutes=1), enabled=True))
        s.add(Reminder(id="rem-2", user_id=8801, title="未来提醒",
                       trigger_at=now + timedelta(days=1), enabled=True))
        s.add(Reminder(id="rem-3", user_id=8801, title="已禁用",
                       trigger_at=now - timedelta(minutes=1), enabled=False))
        s.commit()
    with SessionLocal() as s:
        processed = process_due_reminders(s, now)
    assert processed == 1, "只有 enabled 且到期的触发"

    with SessionLocal() as s:
        r1 = s.query(Reminder).filter(Reminder.id == "rem-1").first()
        assert r1.status == "triggered"
        n = s.query(Notification).filter(Notification.user_id == 8801).first()
        assert n is not None
        assert n.kind == "reminder_due"
        assert n.payload_json == {"reminder_id": "rem-1", "link": "/reminders"}

    unread = c.get("/api/v1/notifications/unread-count").json()
    assert unread["unread"] >= 1


def test_36_repeat_rules_advance_next_trigger(client):
    c, SessionLocal = client
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    base = now - timedelta(minutes=5)

    nxt = compute_next_trigger_at(base, "daily", now)
    assert nxt > now and (nxt - base).days >= 1

    nxt_weekly = compute_next_trigger_at(base, "weekly", now)
    assert (nxt_weekly - base).days >= 7

    nxt_monthly = compute_next_trigger_at(datetime(2026, 1, 31, 12, 0, tzinfo=timezone.utc), "monthly", now)
    assert nxt_monthly is not None
    assert nxt_monthly.day <= 28  # 1/31 → 2/28 钳制

    assert compute_next_trigger_at(base, "none", now) is None

    # 重复提醒到期：推进 trigger_at 并保持 active，且生成通知
    with SessionLocal() as s:
        s.add(Reminder(id="rem-rep", user_id=8801, title="每日复习",
                       trigger_at=base, repeat_rule="daily", enabled=True))
        s.commit()
    with SessionLocal() as s:
        processed = process_due_reminders(s, now)
    assert processed == 1
    with SessionLocal() as s:
        r = s.query(Reminder).filter(Reminder.id == "rem-rep").first()
        assert r.status == "active"
        assert r.trigger_at > now


# ── #39 tip 回源契约 ────────────────────────────────────────

def test_39_tina_message_requires_session(client):
    c, _ = client
    base = {"title": "tip", "content_md": "引用原文", "note_type": "tip", "source": "tina"}
    r = c.post("/api/v1/notes", json={**base, "source_ref_type": "tina_message", "source_ref_id": "msg-1"})
    assert r.status_code == 422  # 缺 source_session_id

    r = c.post("/api/v1/notes", json={**base, "source_ref_type": "tina_message",
                                      "source_ref_id": "msg-1", "source_session_id": "sess-abc"})
    assert r.status_code == 201
    body = r.json()
    assert body["source_ref_type"] == "tina_message"
    assert body["source_session_id"] == "sess-abc"
    # 列表/详情也返回可解析字段
    listed = c.get("/api/v1/notes?note_type=tip").json()
    assert any(x["id"] == body["id"] and x["source_session_id"] == "sess-abc" for x in listed)


def test_39_quiz_session_ownership(client):
    c, SessionLocal = client
    with SessionLocal() as s:
        # 同一 schema 里补种 8802，避免第二个 fixture 重清库破坏本测试数据
        _seed_user(s, 8802, "b@example.com")
        s.add(QuizSession(id="qs-mine", user_id=8801, title="我的刷题"))
        s.add(QuizSession(id="qs-other", user_id=8802, title="别人的"))
        s.commit()
    base = {"title": "tip", "content_md": "引用", "note_type": "tip", "source": "quiz"}

    # 他人会话 → 422
    r = c.post("/api/v1/notes", json={**base, "source_ref_type": "quiz_session", "source_ref_id": "qs-other"})
    assert r.status_code == 422

    # 本人会话 → 201 且返回会话 id
    r = c.post("/api/v1/notes", json={**base, "source_ref_type": "quiz_session", "source_ref_id": "qs-mine"})
    assert r.status_code == 201
    assert r.json()["source_ref_id"] == "qs-mine"


def test_39_document_anchor_regression(client):
    """资料 tip 页码回源不回归。"""
    c, _ = client
    r = c.post("/api/v1/notes", json={
        "title": "书中一段", "content_md": "划线原文", "note_type": "tip",
        "source": "kb", "document_id": "doc-a", "page_number": 12,
        "char_start": 10, "char_end": 20,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["page_number"] == 12 and body["char_start"] == 10
