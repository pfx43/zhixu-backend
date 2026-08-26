"""Issue #18 tip 笔记 — 测试覆盖

验收条件（来自 Issue #18）：
1. 用户 A 的 tip 不会出现在用户 B 的 note_type=tip 列表（用户隔离）。
2. 列表默认新的在前。
3. 关联文档 id 必须属于当前用户，否则拒绝。
4. 知识点 tag 接口不会把 tip 类型混进去。
5. 删号后该用户 tip 为空。
6. tip 走笔记接口 note_type=tip；无 tag 也可收；可按 tag / source 筛选。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from server import app
from app.api.deps import get_db, get_current_user
from app.models import (
    User,
    KbCollection,
    Document,
    UserNote,
    GlobalQuestion,
    QuestionProvenance,
    UserQuestionRef,
)
from app.services.tools.task_tools import TaskPlannerTools


def _create_temp_db():
    return make_sessionmaker()


def _seed_user(session, user_id: int, email: str):
    session.add(User(
        id=user_id,
        email=email,
        password_hash="hashed",
        nickname=f"U{user_id}",
        is_active=True,
    ))
    session.commit()


def _seed_document(session, user_id: int, doc_id: str, name: str = "书.pdf"):
    coll = KbCollection(
        id=f"coll-{doc_id}", user_id=user_id, name="学习区", zone="study", is_default=True
    )
    session.add(coll)
    session.flush()
    doc = Document(
        id=doc_id,
        user_id=user_id,
        collection_id=coll.id,
        display_name=name,
        zone="study",
        content_hash=f"hash-{doc_id}",
        parsed_cache_key=f"parsed-{doc_id}",
        indexing_status="completed",
        segment_status="completed",
        question_gen_status="not_started",
    )
    session.add(doc)
    session.commit()
    return doc


@pytest.fixture()
def tip_client(monkeypatch):
    """主用户（id=8801），含一本自己的文档"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 8801, "email": "tip-a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "tip-a@example.com")
        _seed_document(session, 8801, "doc-a", "A 的书.pdf")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture()
def tip_client_other(monkeypatch):
    """另一用户（id=8802），有自己的一本书 doc-b"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return {"user_id": 8802, "email": "tip-b@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "tip-a@example.com")
        _seed_user(session, 8802, "tip-b@example.com")
        _seed_document(session, 8801, "doc-a", "A 的书.pdf")
        _seed_document(session, 8802, "doc-b", "B 的书.pdf")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


def _create_tip(client, **overrides):
    payload = {
        "title": "易错公式",
        "content_md": "把 x 提到对数前面",
        "note_type": "tip",
        "tags": ["易错点"],
        "document_id": "doc-a",
        "source": "quiz",
    }
    payload.update(overrides)
    return client.post("/api/v1/notes", json=payload)


# ── tip 创建 + 列表（走笔记接口 note_type=tip） ───────────────

def test_create_tip_via_notes_api(tip_client):
    client, SessionLocal = tip_client
    resp = _create_tip(client)
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["note_type"] == "tip"
    assert data["tags"] == ["易错点"]
    assert data["document_id"] == "doc-a"
    assert data["source"] == "quiz"

    # 列表按 note_type=tip 能筛出，新的在前
    resp2 = client.get("/api/v1/notes?note_type=tip")
    assert resp2.status_code == 200
    tips = resp2.json()
    assert len(tips) == 1
    assert tips[0]["id"] == data["id"]


def test_tip_without_tag_is_allowed(tip_client):
    """用户没打 tag 也可以收。"""
    client, _ = tip_client
    resp = _create_tip(client, tags=None, document_id=None, source=None)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tags"] is None
    assert data["document_id"] is None


def test_list_default_newest_first(tip_client):
    client, _ = tip_client
    _create_tip(client, title="tip 一")
    _create_tip(client, title="tip 二")
    resp = client.get("/api/v1/notes?note_type=tip")
    titles = [t["title"] for t in resp.json()]
    assert titles == ["tip 二", "tip 一"]


def test_list_filter_by_tag_and_source(tip_client):
    client, _ = tip_client
    _create_tip(client, title="难词", tags=["英语难词"], source="tina")
    _create_tip(client, title="易错", tags=["易错点"], source="quiz")

    by_tag = client.get("/api/v1/notes?note_type=tip&tag=英语难词").json()
    assert [t["title"] for t in by_tag] == ["难词"]

    by_source = client.get("/api/v1/notes?note_type=tip&source=quiz").json()
    assert [t["title"] for t in by_source] == ["易错"]


# ── 验收 3：关联文档必须属于当前用户 ─────────────────────────

def test_document_id_must_belong_to_current_user(tip_client_other):
    """用他人文档 id 创建 tip → 拒绝（不能编造他人文档 id）。"""
    client, _ = tip_client_other
    resp = _create_tip(client, document_id="doc-a")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "文档不存在"

    # 自己的文档可以
    resp2 = _create_tip(client, document_id="doc-b")
    assert resp2.status_code == 201


# ── 验收 1：用户隔离 ─────────────────────────────────────────

def test_tips_isolated_between_users(tip_client_other):
    client_b, SessionLocal = tip_client_other

    # 先由 A（8801）写一张 tip（直接走库，模拟 A 已收）
    with SessionLocal() as session:
        session.add(UserNote(
            id="tip-a-1",
            user_id=8801,
            title="A 的 tip",
            content_md="内容",
            note_type="tip",
            tags=["难词"],
        ))
        session.commit()

    # B 的 tip 列表看不到 A 的
    resp = client_b.get("/api/v1/notes?note_type=tip")
    assert resp.status_code == 200
    assert resp.json() == []


# ── 验收 5：删号后 tip 为空 ─────────────────────────────────

def test_delete_account_clears_tips(tip_client, monkeypatch):
    from app.services.auth import auth_service
    from app.services.auth.auth_service import AuthManager

    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    client, SessionLocal = tip_client
    _create_tip(client)
    _create_tip(client, title="第二条")

    with SessionLocal() as session:
        assert session.query(UserNote).filter(UserNote.user_id == 8801).count() == 2
        AuthManager.delete_account(session, 8801)
        assert session.query(UserNote).filter(UserNote.user_id == 8801).count() == 0


# ── 验收 4：知识点 tag 接口不会把 tip 类型混进去 ──────────────

def test_knowledge_point_tags_not_mixed(tip_client):
    """题目的知识点 tag（global_questions.tags）与 tip 的用户分类互不污染。"""
    client, SessionLocal = tip_client
    _create_tip(client, tags=["易错点"])

    with SessionLocal() as session:
        q = GlobalQuestion(
            id="q-tag-1",
            content_hash="h-tag-1",
            stem="题",
            question_type="single_choice",
            answer="A",
            source_type="generated",
            tags='["知识点A"]',
        )
        session.add(q)
        session.flush()
        session.add(QuestionProvenance(
            id="prov-tag-1", question_id=q.id, document_id="doc-a", page_number=1,
        ))
        session.add(UserQuestionRef(
            id="ref-tag-1", user_id=8801, question_id=q.id, document_id="doc-a",
        ))
        session.commit()

    # 题目列表里的 tags 是知识点，不含 tip 的「易错点」
    resp = client.get("/api/v1/questions?document_id=doc-a")
    assert resp.status_code == 200
    q_tags = [q["tags"] for q in resp.json()["questions"] if q["tags"]]
    assert q_tags == [["知识点A"]]


# ── Tina 工具：list_tips / create_tip ────────────────────────

def test_tina_create_and_list_tips(tip_client_other):
    """Tina 工具只动当前用户；他人文档 id 被拒；无 tag 可收。"""
    client, SessionLocal = tip_client_other

    tools_b = TaskPlannerTools(user_id=8802)
    import json

    # 用他人文档（doc-a 属于 8801）→ 拒绝
    bad = json.loads(tools_b.create_tip("标题", "内容", document_id="doc-a"))
    assert "error" in bad

    # 用自己的文档 → 成功；用户没说 tag → 为空
    ok = json.loads(tools_b.create_tip("B 的 tip", "内容", document_id="doc-b"))
    assert ok["status"] == "ok"
    assert ok["tip"]["tags"] is None

    # 列表只看到自己的
    tips = json.loads(tools_b.list_tips())["tips"]
    assert len(tips) == 1
    assert tips[0]["title"] == "B 的 tip"
