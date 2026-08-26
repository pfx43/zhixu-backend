"""Issue #19 今日任务 + 检查器 — HTTP 测试覆盖

验收条件（来自 Issue #19）：
1. 无勾选完成的 HTTP 路由（404 / 405）。
2. 上传成功且解析出文本 → 上传类任务进入 completed，响应含该任务 id/title。
3. 同一文件 hash 去重未产生新文档 → 任务仍未完成。
4. 出题只覆盖非 payload 页 → 出题任务未完成；payload 页有题 → 完成。
5. 刷题任务交够道数且含「不会」→ 完成；未交够 → 未完成。
6. 另一用户的任务互不可见；删号后任务为空。
7. 不得把 dashboard/suggestions 或 training_plans 改名为今日任务。
8. ensure 不重复派：有未完成的先展示。
"""
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from server import app
from app.api.deps import get_db, get_current_user
from app.models import (
    User,
    Goal,
    KbCollection,
    Document,
    GlobalQuestion,
    QuestionProvenance,
    UserQuestionRef,
    QuizSession,
    QuizSessionQuestion,
    DailyTask,
)
from app.services.quiz import question_gen_service
from app.services.knowledge import kb_service
from app.services.tasks import task_service


def _create_temp_db():
    return make_sessionmaker()


def _seed_user(session, user_id: int, email: str, nickname: str = "TaskTest"):
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


def _seed_document(session, user_id: int, doc_id: str = "doc-1", name: str = "高等数学.pdf"):
    coll = KbCollection(
        id="coll-1",
        user_id=user_id,
        name="学习区",
        zone="study",
        is_default=True,
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
    session.refresh(doc)
    return doc


def _seed_question_on_page(session, user_id: int, doc_id: str, page: int) -> str:
    """在指定页落一道题（GlobalQuestion + provenance + user ref）。"""
    q = GlobalQuestion(
        id=f"q-{doc_id}-p{page}",
        content_hash=f"hash-q-{doc_id}-p{page}",
        stem=f"第 {page} 页的题",
        question_type="single_choice",
        options='[{"key":"A","text":"对"},{"key":"B","text":"错"}]',
        answer="A",
        explanation="解析",
        source_type="generated",
    )
    session.add(q)
    session.flush()
    session.add(
        QuestionProvenance(
            id=f"prov-{doc_id}-p{page}",
            question_id=q.id,
            document_id=doc_id,
            page_number=page,
        )
    )
    session.add(
        UserQuestionRef(
            id=f"ref-{doc_id}-p{page}",
            user_id=user_id,
            question_id=q.id,
            document_id=doc_id,
        )
    )
    session.commit()
    return q.id


def _seed_pending_task(
    session, user_id: int, task_type: str, payload: dict = None, rule: dict = None
) -> DailyTask:
    task = DailyTask(
        user_id=user_id,
        task_date=task_service.today_local(),
        title=f"{task_type} 任务",
        reason="测试",
        task_type=task_type,
        payload=payload or {},
        completion_rule=rule or {},
        status="pending",
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture()
def task_client(monkeypatch):
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
        return {"user_id": 8801, "email": "task-a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "task-a@example.com", nickname="Alice")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture()
def task_client_other(monkeypatch):
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
        return {"user_id": 8802, "email": "task-b@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with SessionLocal() as session:
        _seed_user(session, 8801, "task-a@example.com", nickname="Alice")
        _seed_user(session, 8802, "task-b@example.com", nickname="Bob")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


# ── 验收 8 / 基础：ensure 不重复派 + 缺口生成 ─────────────────

def test_ensure_generates_upload_when_no_documents(task_client):
    client, SessionLocal = task_client

    # 没书 → 派上传任务
    resp = client.post("/api/v1/tasks/today/ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["tasks"]) == 1
    task = data["tasks"][0]
    assert task["task_type"] == "upload"
    assert task["status"] == "pending"
    assert task["completion_rule"] == {"kind": "new_parsable_document"}

    # 再 ensure → 有未完成的先展示，不重复派
    resp2 = client.post("/api/v1/tasks/today/ensure")
    assert resp2.status_code == 200
    tasks2 = resp2.json()["tasks"]
    assert len(tasks2) == 1
    assert tasks2[0]["id"] == task["id"]

    # GET 也能读到同一条
    resp3 = client.get("/api/v1/tasks/today")
    assert resp3.status_code == 200
    assert [t["id"] for t in resp3.json()["tasks"]] == [task["id"]]


def test_ensure_generates_generate_task_when_book_without_questions(task_client):
    client, SessionLocal = task_client
    with SessionLocal() as session:
        _seed_document(session, 8801, "doc-noq", "线性代数.pdf")
        from app.models import DocumentSegment
        session.add(DocumentSegment(
            id="seg-1",
            document_id="doc-noq",
            order_index=0,
            title="第一章",
            content="内容",
            char_start=0,
            char_end=10,
            page_start=1,
            page_end=3,
        ))
        session.commit()

    resp = client.post("/api/v1/tasks/today/ensure")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    gen_tasks = [t for t in tasks if t["task_type"] == "generate_questions"]
    assert len(gen_tasks) == 1
    # 页码来自入库分段（page_start），不是模型手填
    assert gen_tasks[0]["payload"]["document_id"] == "doc-noq"
    assert set(gen_tasks[0]["payload"]["page_numbers"]) <= {1, 2, 3}


def test_ensure_generates_practice_when_questions_exist(task_client):
    client, SessionLocal = task_client
    with SessionLocal() as session:
        doc = _seed_document(session, 8801, "doc-q", "概率论.pdf")
        _seed_question_on_page(session, 8801, doc.id, 1)
        _seed_question_on_page(session, 8801, doc.id, 2)
        session.commit()

    resp = client.post("/api/v1/tasks/today/ensure")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    practice_tasks = [t for t in tasks if t["task_type"] == "practice"]
    assert len(practice_tasks) == 1
    assert practice_tasks[0]["completion_rule"]["count"] == 2


# ── 验收 2/3：上传检查器 ──────────────────────────────────────

def _patch_upload(monkeypatch, status: str = "indexing", segment_status: str = "completed"):
    def fake_upload(**kwargs):
        from app.schemas.kb import UploadResponse
        return UploadResponse(
            message="文件已上传",
            id="new-doc-1",
            file_name="别处的书.pdf",
            status=status,
            segment_status=segment_status,
        )

    monkeypatch.setattr(kb_service, "upload_document", fake_upload)


def test_upload_completes_upload_task(task_client, monkeypatch):
    client, SessionLocal = task_client
    with SessionLocal() as session:
        task = _seed_pending_task(session, 8801, "upload")
    _patch_upload(monkeypatch)

    resp = client.post("/api/v1/kb/upload", files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert resp.status_code == 200
    data = resp.json()
    ids = [r["id"] for r in data["completed_tasks"]]
    assert task.id in ids
    rec = next(r for r in data["completed_tasks"] if r["id"] == task.id)
    assert rec["title"] == task.title
    assert rec["source_action"] == "upload"
    assert rec["after_status"] == "completed"
    assert "idempotency_key" in rec

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "completed"


def test_upload_wrong_book_still_completes(task_client, monkeypatch):
    """传的不是任务里说的那本书：这一期仍然算完成（检查器不做语义判断）。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        task = _seed_pending_task(
            session, 8801, "upload",
            payload={"expectation": "高等数学.pdf"},
        )
    _patch_upload(monkeypatch)

    resp = client.post("/api/v1/kb/upload", files={"file": ("别处的书.pdf", b"other", "application/pdf")})
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["completed_tasks"]]
    assert task.id in ids
    rec = next(r for r in resp.json()["completed_tasks"] if r["id"] == task.id)
    assert rec["title"] == task.title
    assert rec["source_action"] == "upload"


def test_upload_duplicate_does_not_complete(task_client, monkeypatch):
    """同一文件 hash 去重未产生新文档 → 任务仍未完成。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        task = _seed_pending_task(session, 8801, "upload")
    _patch_upload(monkeypatch, status="duplicate", segment_status="completed")

    resp = client.post("/api/v1/kb/upload", files={"file": ("test.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert resp.status_code == 200
    assert resp.json()["completed_tasks"] == []

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "pending"


def test_upload_parse_failure_does_not_complete(task_client, monkeypatch):
    """解析失败 → 学习区没有多出能解析的书 → 任务继续挂。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        task = _seed_pending_task(session, 8801, "upload")
    _patch_upload(monkeypatch, status="error", segment_status="failed")

    resp = client.post("/api/v1/kb/upload", files={"file": ("bad.pdf", b"", "application/pdf")})
    assert resp.status_code == 200
    assert resp.json()["completed_tasks"] == []

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "pending"


# ── 验收 4：出题检查器 ───────────────────────────────────────

def _patch_generate_pages(monkeypatch, document_id: str, page_numbers):
    async def fake_generate_from_pages(**kwargs):
        from app.schemas.question import PageQuestionResponse
        return PageQuestionResponse(
            document_id=document_id,
            page_numbers=list(page_numbers),
            mode="generate",
            questions_created=0,
            questions_reused=0,
            total_questions=0,
        )

    monkeypatch.setattr(question_gen_service, "is_question_gen_async", lambda: False)
    monkeypatch.setattr(question_gen_service, "generate_from_pages", fake_generate_from_pages)


def _post_generate(client, document_id="doc-1", pages=None):
    return client.post(
        "/api/v1/questions/generate-from-pages",
        json={"document_id": document_id, "page_numbers": pages or [1, 2]},
        headers={"Authorization": "Bearer TEST_TOKEN_FOR_USER"},
    )


def test_generate_completes_when_payload_pages_have_questions(task_client, monkeypatch):
    client, SessionLocal = task_client
    with SessionLocal() as session:
        doc = _seed_document(session, 8801, "doc-1", "高数.pdf")
        # payload 页 [1,2] 都有题
        _seed_question_on_page(session, 8801, doc.id, 1)
        _seed_question_on_page(session, 8801, doc.id, 2)
        task = _seed_pending_task(
            session, 8801, "generate_questions",
            payload={"document_id": "doc-1", "page_numbers": [1, 2]},
            rule={"kind": "pages_have_questions", "document_id": "doc-1", "page_numbers": [1, 2]},
        )
    _patch_generate_pages(monkeypatch, "doc-1", [1, 2])

    resp = _post_generate(client)
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["completed_tasks"]]
    assert task.id in ids
    rec = next(r for r in resp.json()["completed_tasks"] if r["id"] == task.id)
    assert rec["title"] == task.title
    assert rec["source_action"] == "generate_questions"

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "completed"


def test_generate_wrong_pages_does_not_complete(task_client, monkeypatch):
    """只出了别的页（payload 页仍空）→ 任务继续挂。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        doc = _seed_document(session, 8801, "doc-1", "高数.pdf")
        _seed_question_on_page(session, 8801, doc.id, 3)  # 只有第 3 页有题
        task = _seed_pending_task(
            session, 8801, "generate_questions",
            payload={"document_id": "doc-1", "page_numbers": [1, 2]},
            rule={"kind": "pages_have_questions", "document_id": "doc-1", "page_numbers": [1, 2]},
        )
    # 本次操作只覆盖页 3（与 payload 无关），但检查器只看 payload 页是否已有题
    _patch_generate_pages(monkeypatch, "doc-1", [3])

    resp = _post_generate(client, pages=[3])
    assert resp.status_code == 200
    assert resp.json()["completed_tasks"] == []

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "pending"


# ── 验收 5：交卷检查器 ───────────────────────────────────────

def _create_quiz_session(client, doc_id="doc-1", question_ids=None):
    return client.post(
        "/api/v1/quiz/sessions",
        json={
            "document_id": doc_id,
            "question_ids": question_ids or ["q-doc-1-p1", "q-doc-1-p2"],
            "title": "刷题测试",
        },
    )


def test_practice_completes_when_count_reached_with_unknown(task_client):
    """交够约定道数（含「不会」unknown）→ 完成。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        doc = _seed_document(session, 8801, "doc-1", "高数.pdf")
        _seed_question_on_page(session, 8801, doc.id, 1)
        _seed_question_on_page(session, 8801, doc.id, 2)
        task = _seed_pending_task(
            session, 8801, "practice",
            payload={"document_id": "doc-1", "count": 2},
            rule={"kind": "practice_count", "document_id": "doc-1", "count": 2},
        )

    r = _create_quiz_session(client)
    assert r.status_code == 201
    session_id = r.json()["id"]

    # 第一题正确
    r1 = client.post(f"/api/v1/quiz/sessions/{session_id}/answers",
                     json={"question_id": "q-doc-1-p1", "user_answer": "A"})
    assert r1.status_code == 200
    assert r1.json()["completed_tasks"] == []  # 未交够

    # 第二题「我不会」（unknown）也算
    r2 = client.post(f"/api/v1/quiz/sessions/{session_id}/answers",
                     json={"question_id": "q-doc-1-p2", "status": "unknown"})
    assert r2.status_code == 200
    ids = [r["id"] for r in r2.json()["completed_tasks"]]
    assert task.id in ids
    rec = next(r for r in r2.json()["completed_tasks"] if r["id"] == task.id)
    assert rec["title"] == task.title
    assert rec["source_action"] == "answer_submitted"

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "completed"


def test_practice_not_complete_when_insufficient(task_client):
    client, SessionLocal = task_client
    with SessionLocal() as session:
        doc = _seed_document(session, 8801, "doc-1", "高数.pdf")
        _seed_question_on_page(session, 8801, doc.id, 1)
        _seed_question_on_page(session, 8801, doc.id, 2)
        task = _seed_pending_task(
            session, 8801, "practice",
            payload={"document_id": "doc-1", "count": 5},
            rule={"kind": "practice_count", "document_id": "doc-1", "count": 5},
        )

    r = _create_quiz_session(client)
    session_id = r.json()["id"]
    r1 = client.post(f"/api/v1/quiz/sessions/{session_id}/answers",
                     json={"question_id": "q-doc-1-p1", "user_answer": "A"})
    assert r1.json()["completed_tasks"] == []  # 2/5 未交够

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "pending"


# ── 验收 6：用户隔离 + 删号级联 ───────────────────────────────

def test_tasks_isolated_between_users(task_client_other):
    client, SessionLocal = task_client_other
    with SessionLocal() as session:
        _seed_pending_task(session, 8801, "upload")
        _seed_pending_task(session, 8801, "upload")

    # 8802 看不到 8801 的任务
    resp = client.get("/api/v1/tasks/today")
    assert resp.status_code == 200
    assert resp.json()["tasks"] == []


def test_other_user_upload_does_not_complete_my_task(task_client_other, monkeypatch):
    client, SessionLocal = task_client_other
    with SessionLocal() as session:
        task = _seed_pending_task(session, 8801, "upload")
    _patch_upload(monkeypatch)

    # 8802 上传自己的书 → 不影响 8801 的任务
    resp = client.post("/api/v1/kb/upload", files={"file": ("b.pdf", b"bbb", "application/pdf")})
    assert resp.status_code == 200
    assert resp.json()["completed_tasks"] == []

    with SessionLocal() as session:
        t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
        assert t.status == "pending"


def test_delete_account_cascades_daily_tasks(task_client, monkeypatch):
    from app.services.auth import auth_service
    from app.services.auth.auth_service import AuthManager

    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    client, SessionLocal = task_client
    with SessionLocal() as session:
        _seed_pending_task(session, 8801, "upload")
        _seed_pending_task(session, 8801, "generate_questions")

    with SessionLocal() as session:
        assert session.query(DailyTask).filter(DailyTask.user_id == 8801).count() == 2
        AuthManager.delete_account(session, 8801)
        assert session.query(DailyTask).filter(DailyTask.user_id == 8801).count() == 0


# ── 验收 1/7：无勾选接口、不用 suggestions 冒充 ────────────────

def test_no_checkoff_endpoint(task_client):
    client, _ = task_client
    r = client.patch("/api/v1/tasks/1/complete", json={"status": "completed"})
    assert r.status_code in (404, 405)
    r2 = client.post("/api/v1/tasks/complete", json={"id": 1})
    assert r2.status_code in (404, 405)


def test_today_returns_only_daily_tasks(task_client):
    """今日任务来自 daily_tasks，而不是 dashboard/suggestions 或 training_plans。"""
    client, SessionLocal = task_client
    with SessionLocal() as session:
        _seed_pending_task(session, 8801, "upload")
        _seed_pending_task(session, 8801, "generate_questions")

    resp = client.get("/api/v1/tasks/today")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 2
    assert all(t["task_type"] in ("upload", "generate_questions", "practice") for t in tasks)
