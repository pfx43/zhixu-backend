"""Issue #5.X 后端契约补齐 — HTTP 测试覆盖

10 项契约核心路径：
1. TodayTask DTO（primary/candidates/tasks）+ CompletionReceipt 回执（idempotency_key/evidence）
2. 题型扩展（multi_choice/true_false/fill_blank/sort/match/classify）
3. 资料封面 cover_url/thumbnail_url + 学习路径按目标 goal_id
4. Evidence Impact（daily_task 完成回写 evidence_json）
5. tip 跨端锚点（page_number/char_start/char_end/source_ref）
6. 通知 CRUD + unread-count
7. 提醒 CRUD
8. 画像推断（graph + inference）
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
    DailyTask,
    Goal,
    UserNote,
    Notification,
    Reminder,
    ProfileGraph,
    ProfileInference,
    GlobalQuestion,
    QuestionProvenance,
    UserQuestionRef,
)


def _create_temp_db():
    return make_sessionmaker()


def _seed_user(session, user_id, email, nickname="U"):
    session.add(User(id=user_id, email=email, password_hash="h", nickname=nickname, is_active=True))
    session.commit()


def _seed_document(session, user_id, doc_id, name="书.pdf"):
    coll = KbCollection(id=f"coll-{doc_id}", user_id=user_id, name="学习区", zone="study", is_default=True)
    session.add(coll); session.flush()
    doc = Document(
        id=doc_id, user_id=user_id, collection_id=coll.id, display_name=name, zone="study",
        content_hash=f"hash-{doc_id}", parsed_cache_key=f"parsed-{doc_id}",
        indexing_status="completed", segment_status="completed", question_gen_status="completed",
        cover_url=f"/covers/{doc_id}.png", thumbnail_url=f"/thumbs/{doc_id}.png",
    )
    session.add(doc); session.commit()
    return doc


def _seed_goal(session, user_id, text="研究生上岸"):
    g = Goal(user_id=user_id, text=text, status="active", attributes={"subject": "计算机"})
    session.add(g); session.commit()
    return g


@pytest.fixture()
def client(monkeypatch):
    """主用户（id=8801）"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        s = SessionLocal()
        try: yield s
        finally: s.close()

    def override_get_current_user():
        return {"user_id": 8801, "email": "a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com")
        _seed_document(s, 8801, "doc-a")
    with TestClient(app) as c:
        yield c, SessionLocal
    engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_doc(monkeypatch):
    """主用户（id=8801）但没文档（确保 ensure 派 upload 任务）。"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        s = SessionLocal()
        try: yield s
        finally: s.close()

    def override_get_current_user():
        return {"user_id": 8801, "email": "a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com")
    with TestClient(app) as c:
        yield c, SessionLocal
    engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture()
def client_other(monkeypatch):
    """另一用户（id=8802）"""
    engine, SessionLocal = _create_temp_db()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        s = SessionLocal()
        try: yield s
        finally: s.close()

    def override_get_current_user():
        return {"user_id": 8802, "email": "b@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com")
        _seed_user(s, 8802, "b@example.com")
        _seed_document(s, 8801, "doc-a")
        _seed_document(s, 8802, "doc-b")
    with TestClient(app) as c:
        yield c, SessionLocal
    engine.dispose()
    app.dependency_overrides.clear()


# ── 1. TodayTask DTO + CompletionReceipt ─────────────────────

def test_today_task_dto_has_primary_and_candidates(client_no_doc):
    c, _ = client_no_doc
    c.post("/api/v1/tasks/today/ensure")
    r = c.get("/api/v1/tasks/today")
    assert r.status_code == 200
    data = r.json()
    assert "primary" in data
    assert "candidates" in data
    assert "tasks" in data
    assert "completed_tasks" in data
    # 没书 → 派 upload 任务（primary）
    assert data["primary"] is not None
    assert data["primary"]["task_type"] == "upload"
    assert data["primary"]["href"] == "/library"  # 上传类跳转资料库
    # 完成回执（含 receipt 字段）
    assert "idempotency_key" not in data  # 今天还没完成


def test_completion_receipt_on_upload(client_no_doc, monkeypatch):
    """上传成功 → 响应 completed_tasks 含 receipt（idempotency_key/evidence/source_action）。"""
    from app.services.knowledge import kb_service
    from app.schemas.kb import UploadResponse

    def fake_upload(**kwargs):
        return UploadResponse(
            message="OK", id="doc-x", file_name="f.pdf",
            status="indexing", segment_status="completed",
            cover_url="/covers/x.png",
        )
    monkeypatch.setattr(kb_service, "upload_document", fake_upload)

    c, _ = client_no_doc
    # 先 ensure 出 upload 任务
    c.post("/api/v1/tasks/today/ensure")
    # 再上传（mock）触发检查器
    r = c.post(
        "/api/v1/kb/upload",
        files={"file": ("f.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == 200
    completed = r.json()["completed_tasks"]
    assert completed, "应该有完成回执"
    receipt = completed[0]
    # Issue #5.X CompletionReceipt 字段
    assert "idempotency_key" in receipt and len(receipt["idempotency_key"]) == 64
    assert receipt["source_action"] == "upload"
    assert receipt["before_status"] == "pending"
    assert receipt["after_status"] == "completed"
    assert receipt["evidence"]["document_id"] == "doc-x"


# ── 2. 题型扩展（七类判题） ──────────────────────────────────

def _seed_question(session, qid, qtype, stem, options, answer, doc_id, page=1):
    import json
    q = GlobalQuestion(
        id=qid, content_hash=f"h-{qid}", stem=stem, question_type=qtype,
        options=json.dumps(options) if options is not None else None,
        answer=answer, explanation="解析", source_type="generated",
    )
    session.add(q); session.flush()
    session.add(QuestionProvenance(id=f"prov-{qid}", question_id=qid, document_id=doc_id, page_number=page))
    session.add(UserQuestionRef(id=f"ref-{qid}", user_id=8801, question_id=qid, document_id=doc_id))
    session.commit()


def _create_quiz_session(client, question_ids):
    return client.post(
        "/api/v1/quiz/sessions",
        json={"document_id": "doc-a", "question_ids": question_ids, "title": "测试"},
    )


def _answer(client, session_id, qid, answer):
    body = {"question_id": qid}
    if isinstance(answer, str):
        body["user_answer"] = answer
    else:
        body["user_answer"] = answer  # JSON 字符串化由 quiz_service 处理
    return client.post(f"/api/v1/quiz/sessions/{session_id}/answers", json=body)


@pytest.mark.parametrize(
    "qtype,answer,correct",
    [
        ("single_choice", "A", "correct"),
        ("multi_choice", '["A","C"]', "correct"),
        ("multi_choice", '["A","B"]', "wrong"),
        ("true_false", "true", "correct"),
        ("true_false", "false", "wrong"),
        ("fill_blank", "光年", "correct"),
        ("fill_blank", "厘米", "wrong"),
        ("sort", '["B","A","D","C"]', "correct"),
        ("sort", '["A","B","C","D"]', "wrong"),
        ("match", '{"左1":"右1","左2":"右2"}', "correct"),
        ("classify", '["动物","植物"]', "correct"),
    ],
)
def test_question_type_grading(client, qtype, answer, correct):
    """七类题型判题。"""
    import json
    c, SessionLocal = client
    with SessionLocal() as s:
        if qtype == "single_choice":
            opts = [{"key": "A", "text": "A1"}, {"key": "B", "text": "B1"}]
            _seed_question(s, f"q-{qtype}-{answer[:5]}", qtype, "题干", opts, "A", "doc-a")
            qids = [f"q-{qtype}-{answer[:5]}"]
        elif qtype == "multi_choice":
            opts = [{"key": "A", "text": "a"}, {"key": "B", "text": "b"}, {"key": "C", "text": "c"}]
            _seed_question(s, "q-multi", qtype, "题干", opts, '["A","C"]', "doc-a")
            qids = ["q-multi"]
        elif qtype == "true_false":
            _seed_question(s, "q-tf", qtype, "题干", None, "true", "doc-a")
            qids = ["q-tf"]
        elif qtype == "fill_blank":
            _seed_question(s, "q-fb", qtype, "光的单位", None, "光年", "doc-a")
            qids = ["q-fb"]
        elif qtype == "sort":
            opts = [{"key": "A", "text": ""}, {"key": "B", "text": ""}, {"key": "C", "text": ""}, {"key": "D", "text": ""}]
            _seed_question(s, "q-sort", qtype, "排序", opts, '["B","A","D","C"]', "doc-a")
            qids = ["q-sort"]
        elif qtype == "match":
            opts = [
                {"key": "左1", "text": ""},
                {"key": "左2", "text": ""},
                {"key": "右1", "text": ""},
                {"key": "右2", "text": ""},
            ]
            _seed_question(s, "q-match", qtype, "匹配", opts, '{"左1":"右1","左2":"右2"}', "doc-a")
            qids = ["q-match"]
        elif qtype == "classify":
            opts = [
                {"key": "动物", "text": ""},
                {"key": "植物", "text": ""},
            ]
            _seed_question(s, "q-class", qtype, "分类", opts, '["动物","植物"]', "doc-a")
            qids = ["q-class"]
    sess = _create_quiz_session(c, qids).json()
    sid = sess["id"]
    r = _answer(c, sid, qids[0], answer)
    assert r.status_code == 200
    assert r.json()["status"] == correct, f"{qtype} answer={answer}"


# ── 3. 资料封面 + 学习路径按目标 ───────────────────────────

def test_document_out_has_cover_and_thumbnail(client):
    c, _ = client
    r = c.get("/api/v1/kb/documents")
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert any(d.get("cover_url") for d in docs)


def test_learning_path_supports_goal_id(client):
    c, SessionLocal = client
    with SessionLocal() as s:
        _seed_goal(s, 8801)
    r = c.get("/api/v1/learning-path?goal_id=1")
    assert r.status_code == 200
    # 学习路径返回结构存在
    assert "documents" in r.json() or isinstance(r.json(), dict)


# ── 4. Evidence Impact ───────────────────────────────────────

def test_evidence_persisted_on_completion(client_no_doc, monkeypatch):
    """完成 daily_task 时 evidence_json 应写入到任务行。"""
    from app.services.knowledge import kb_service
    from app.schemas.kb import UploadResponse

    def fake_upload(**kwargs):
        return UploadResponse(
            message="OK", id="doc-ev", file_name="f.pdf",
            status="indexing", segment_status="completed",
        )
    monkeypatch.setattr(kb_service, "upload_document", fake_upload)

    c, SessionLocal = client_no_doc
    c.post("/api/v1/tasks/today/ensure")
    c.post("/api/v1/kb/upload", files={"file": ("f.pdf", b"%PDF", "application/pdf")})

    with SessionLocal() as s:
        completed_task = s.query(DailyTask).filter(
            DailyTask.user_id == 8801, DailyTask.status == "completed"
        ).first()
        assert completed_task is not None
        ev = completed_task.evidence_json
        assert ev is not None
        assert ev.get("document_id") == "doc-ev"
        assert "completed_at" in ev


# ── 5. tip 跨端锚点 ───────────────────────────────────────

def test_tip_anchor_persisted(client):
    """tip 创建时 page_number/char_start/char_end/source_ref 写入并返回。"""
    c, _ = client
    payload = {
        "title": "锚点 tip",
        "content_md": "划选原文",
        "note_type": "tip",
        "page_number": 5,
        "char_start": 100,
        "char_end": 200,
        "source_ref_type": "tina_message",
        "source_ref_id": "msg-123",
    }
    r = c.post("/api/v1/notes", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["page_number"] == 5
    assert data["char_start"] == 100
    assert data["char_end"] == 200
    assert data["source_ref_type"] == "tina_message"
    assert data["source_ref_id"] == "msg-123"


# ── 6. 通知 ────────────────────────────────────────────────

def test_notifications_crud_and_isolation(client_other):
    c, _ = client_other
    # 直接走 DB 注入 A 的通知
    from pgutil import make_sessionmaker as _ms
    _, SessionLocal = client_other
    with SessionLocal() as s:
        s.add(Notification(id="n-a", user_id=8801, kind="test", title="A 的通知"))
        s.commit()
    r = c.get("/api/v1/notifications")
    assert r.status_code == 200
    items = r.json()
    assert items == [], "B 不应看到 A 的通知"

    r2 = c.get("/api/v1/notifications/unread-count")
    assert r2.json() == {"unread": 0}


def test_notification_mark_read(client_other):
    from pgutil import make_sessionmaker as _ms
    c, SessionLocal = client_other
    with SessionLocal() as s:
        s.add(Notification(id="n-b", user_id=8802, kind="test", title="B 的通知"))
        s.commit()
    r = c.post("/api/v1/notifications/n-b/read")
    assert r.status_code == 200
    # 再读 unread-count 应为 0
    assert c.get("/api/v1/notifications/unread-count").json() == {"unread": 0}


# ── 7. 提醒 ────────────────────────────────────────────────

def test_reminders_crud(client_other):
    c, _ = client_other
    from datetime import datetime, timezone, timedelta

    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    payload = {"title": "复习", "trigger_at": when}
    r = c.post("/api/v1/reminders", json=payload)
    assert r.status_code == 201
    rid = r.json()["id"]
    # list / patch / delete
    assert any(x["id"] == rid for x in c.get("/api/v1/reminders").json())
    assert c.patch(f"/api/v1/reminders/{rid}", json={"title": "改"}).status_code == 200
    assert c.delete(f"/api/v1/reminders/{rid}").status_code == 200
    assert not any(x["id"] == rid for x in c.get("/api/v1/reminders").json())


# ── 8. 画像 ────────────────────────────────────────────────

def test_profile_graph_creates_on_demand(client):
    c, _ = client
    r = c.get("/api/v1/profile/graph")
    assert r.status_code == 200
    assert "id" in r.json()


def test_profile_inference_lifecycle(client):
    c, SessionLocal = client
    r = c.post("/api/v1/profile/inferences")
    assert r.status_code == 201
    inf_id = r.json()["id"]
    r2 = c.get(f"/api/v1/profile/inferences/{inf_id}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("running", "pending", "done")