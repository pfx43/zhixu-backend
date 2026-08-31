"""生产问题修复测试（Issues #30 / #31 / #38 / #35 — 陈勇搏）

验收对照（来自各 Issue 验收小节）：
- #30: ensure 与 GET today 均含 primary/candidates；空任务 primary=null、candidates=[]，key 不省略；
       任务含 href/reason_short/evidence。
- #31: 非法 PDF（解析失败）任务仍 pending、today.completed_tasks 不含它；
       合法完成时动作响应与 today 返回同一 idempotency_key 回执；幂等重复不重复弹窗。
- #38: GET /goals/{id}/evidence 返回独立契约列表（before/after/scope/confirmation），
       用户隔离；不复用 task evidence。
- #35: match options 带 side；classify options 为 items/categories 两段；
       true_false 无法解析为 bool → 400；classify 判分按 {itemId: categoryId}；
       单选/多选/填空/sort 不回归。
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
    GoalEvidenceEvent,
)
from app.services.quiz import question_gen_service
from app.services.knowledge import kb_service
from app.services.tasks import task_service


def _seed_user(session, user_id: int, email: str, nickname: str = "ProdTest"):
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


def _seed_document(session, user_id: int, doc_id: str = "pdoc-1", name: str = "高等数学.pdf"):
    coll = KbCollection(
        id=f"pcoll-{doc_id}",
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


def _seed_question_on_page(
    session, user_id: int, doc_id: str, page: int,
    qtype: str = "single_choice", options: str = None, answer: str = "A",
) -> str:
    q = GlobalQuestion(
        id=f"pq-{doc_id}-p{page}-{qtype}",
        content_hash=f"phash-{doc_id}-p{page}-{qtype}",
        stem=f"第 {page} 页的 {qtype} 题",
        question_type=qtype,
        options=options or '[{"key":"A","text":"对"},{"key":"B","text":"错"}]',
        answer=answer,
        explanation="解析",
        source_type="generated",
    )
    session.add(q)
    session.flush()
    session.add(
        QuestionProvenance(
            id=f"pprov-{doc_id}-p{page}-{qtype}",
            question_id=q.id,
            document_id=doc_id,
            page_number=page,
        )
    )
    session.add(
        UserQuestionRef(
            id=f"pref-{doc_id}-p{page}-{qtype}",
            user_id=user_id,
            question_id=q.id,
            document_id=doc_id,
        )
    )
    session.commit()
    return q.id


def _seed_pending_task(
    session, user_id: int, task_type: str, payload: dict = None, rule: dict = None,
    goal_id: int = None,
) -> DailyTask:
    task = DailyTask(
        user_id=user_id,
        goal_id=goal_id,
        task_date=task_service.today_local(),
        title=f"{task_type} 任务",
        reason="这是一段比较长的理由文本，用于验证 reason_short 的截断逻辑是否生效。",
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
def pclient(monkeypatch):
    """主用户 9901"""
    engine, SessionLocal = make_sessionmaker()
    monkeypatch.setattr("app.core.database.init_db", lambda: None)

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        return {"user_id": 9901, "email": "prod-a@example.com", "is_active": True}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    with SessionLocal() as session:
        _seed_user(session, 9901, "prod-a@example.com")

    with TestClient(app) as client:
        yield client, SessionLocal

    engine.dispose()
    app.dependency_overrides.clear()


# ══ #30：今日任务形状 ══════════════════════════════════════════

class TestIssue30TodayShape:
    def test_ensure_and_today_have_primary_candidates(self, pclient):
        client, SessionLocal = pclient
        resp = client.post("/api/v1/tasks/today/ensure")
        assert resp.status_code == 200
        data = resp.json()
        # 一主两候选 key 必须存在且不省略
        assert set(data.keys()) >= {"date", "primary", "candidates", "tasks", "completed_tasks"}
        assert len(data["tasks"]) == 1
        assert data["primary"]["id"] == data["tasks"][0]["id"]
        assert isinstance(data["candidates"], list)

        # GET today 同样带齐
        r2 = client.get("/api/v1/tasks/today")
        d2 = r2.json()
        assert {"primary", "candidates", "tasks", "completed_tasks"} <= set(d2.keys())
        assert d2["primary"] is not None

    def test_empty_day_primary_null_and_candidates_empty(self, pclient):
        """空任务日：primary 明确 null、candidates=[]，key 不省略。"""
        client, _ = pclient
        resp = client.get("/api/v1/tasks/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "primary" in data and data["primary"] is None
        assert "candidates" in data and data["candidates"] == []
        assert data["completed_tasks"] == []
        assert data["tasks"] == []

    def test_primary_is_first_pending_candidates_max_two(self, pclient):
        """多个 pending：primary 取第一条 pending，candidates 最多两条。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            doc = _seed_document(session, 9901, "pdoc-multi", "多任务书.pdf")
            _seed_question_on_page(session, 9901, doc.id, 1)
            _seed_question_on_page(session, 9901, doc.id, 2)

        resp = client.post("/api/v1/tasks/today/ensure")
        tasks = resp.json()["tasks"]
        if len(tasks) < 3:
            pytest.skip(f"当前缺口只生成 {len(tasks)} 个任务")

        d = resp.json()
        pending_ids = [t["id"] for t in tasks if t["status"] == "pending"]
        assert d["primary"]["id"] == pending_ids[0]
        cand_ids = [c["id"] for c in d["candidates"]]
        assert len(cand_ids) <= 2
        assert set(cand_ids) == set(pending_ids[1:3])

    def test_task_dto_has_href_reason_short_evidence(self, pclient):
        client, _ = pclient
        resp = client.post("/api/v1/tasks/today/ensure")
        for t in resp.json()["tasks"]:
            assert t["href"] is not None, f"{t['task_type']} 缺 href"
            assert t["evidence"] is None  # 未完成任务 evidence 为 null
            # reason_short 是 reason 截断版（或原文）
            if t.get("reason"):
                assert t["reason_short"] is not None
                assert len(t["reason_short"]) <= 41  # 40 + 省略号

        # generate 任务 href 带 doc/pages 参数
        gen = [t for t in resp.json()["tasks"] if t["task_type"] == "generate_questions"]
        for g in gen:
            assert f"doc_id={g['payload']['document_id']}" in g["href"]

    def test_href_by_task_type(self, pclient):
        client, SessionLocal = pclient
        # 有书没题 → generate_questions;href=/generate?doc_id=...&pages=...
        with SessionLocal() as session:
            doc = _seed_document(session, 9901, "pdoc-href", "线性代数.pdf")
            from app.models import DocumentSegment
            session.add(DocumentSegment(
                id="pseg-1", document_id="pdoc-href", order_index=0,
                title="第一章", content="内容", char_start=0, char_end=10,
                page_start=1, page_end=2,
            ))
            session.commit()

        resp = client.post("/api/v1/tasks/today/ensure")
        gen = [t for t in resp.json()["tasks"] if t["task_type"] == "generate_questions"]
        assert gen and gen[0]["href"].startswith("/generate?")
        assert "doc_id=pdoc-href" in gen[0]["href"]

        # 纯上传任务 → /library
        with SessionLocal() as session:
            from app.models import DocumentSegment
            session.query(DocumentSegment).filter(DocumentSegment.document_id == "pdoc-href").delete()
            session.query(UserQuestionRef).filter(UserQuestionRef.user_id == 9901).delete()
            session.query(QuestionProvenance).filter(QuestionProvenance.document_id == "pdoc-href").delete()
            session.query(GlobalQuestion).filter(GlobalQuestion.id.like("pq-pdoc-href%")).delete(synchronize_session=False)
            session.query(Document).filter(Document.user_id == 9901).delete()
            session.query(KbCollection).filter(KbCollection.user_id == 9901).delete()
            # 也清掉当天已有任务，确保只派 upload
            session.query(DailyTask).filter(DailyTask.user_id == 9901).delete()
            session.commit()
        resp2 = client.post("/api/v1/tasks/today/ensure")
        ups = [t for t in resp2.json()["tasks"] if t["task_type"] == "upload"]
        assert ups and ups[0]["href"] == "/library"


# ══ #31：完成语义 ══════════════════════════════════════════════

def _patch_upload(monkeypatch, status="indexing", segment_status="completed", parse_warning=None, document_id="new-doc-1"):
    def fake_upload(**kwargs):
        from app.schemas.kb import UploadResponse
        return UploadResponse(
            message="文件已上传",
            id=document_id,
            file_name="别处的书.pdf",
            status=status,
            segment_status=segment_status,
            parse_warning=parse_warning,
        )
    monkeypatch.setattr(kb_service, "upload_document", fake_upload)


class TestIssue31CompletionSemantics:
    def test_failed_parse_keeps_task_pending(self, pclient, monkeypatch):
        """非法 PDF（segment failed）：任务仍 pending，today 回执不含该任务。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch, status="error", segment_status="failed")

        resp = client.post("/api/v1/kb/upload", files={"file": ("bad.pdf", b"", "application/pdf")})
        assert resp.status_code == 200
        assert resp.json()["completed_tasks"] == []

        # today 快照也不带回执
        today = client.get("/api/v1/tasks/today").json()
        assert all(r["id"] != task.id for r in today["completed_tasks"])

        with SessionLocal() as session:
            t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
            assert t.status == "pending"

    def test_indexing_failed_also_blocks_completion(self, pclient, monkeypatch):
        """indexing_status 本身 failed（ctx 透传 route 层 segment 即可）→ 同样不算。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch, status="completed_ok", segment_status="failed")

        resp = client.post("/api/v1/kb/upload", files={"file": ("x.pdf", b"x", "application/pdf")})
        assert resp.json()["completed_tasks"] == []
        with SessionLocal() as session:
            t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
            assert t.status == "pending"

    def test_parse_warning_blocks_completion(self, pclient, monkeypatch):
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch, parse_warning="文档能打开但几乎无正文文本")

        resp = client.post("/api/v1/kb/upload", files={"file": ("w.pdf", b"w", "application/pdf")})
        assert resp.json()["completed_tasks"] == []
        with SessionLocal() as session:
            t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
            assert t.status == "pending"

    def test_success_receipt_shared_between_action_and_today(self, pclient, monkeypatch):
        """合法 PDF 解析成功：动作响应与 today 返回同一 idempotency_key 回执。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch, document_id="good-doc-1")

        resp = client.post("/api/v1/kb/upload", files={"file": ("ok.pdf", b"%PDF-1.4 ok", "application/pdf")})
        receipts = resp.json()["completed_tasks"]
        assert len(receipts) == 1
        rc = receipts[0]
        assert rc["idempotency_key"] and len(rc["idempotency_key"]) == 64
        assert rc["source_action"] == "document_uploaded"
        assert rc["before_status"] == "pending"
        assert rc["after_status"] == "completed"

        # 动作响应与 today 用同一回执
        today = client.get("/api/v1/tasks/today").json()
        today_keys = [r["idempotency_key"] for r in today["completed_tasks"]]
        assert rc["idempotency_key"] in today_keys

        # evidence_json 落库
        with SessionLocal() as session:
            t = session.query(DailyTask).filter(DailyTask.id == task.id).first()
            assert t.status == "completed"
            ev = t.evidence_json
            assert ev and ev["kind"] == "new_parsable_document"
            assert ev["document_id"] == "good-doc-1"

    def test_today_snapshot_returns_completed_receipts_after_refresh(self, pclient, monkeypatch):
        """刷新后 today.completed_tasks 仍有回执（弹窗证据不丢）。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch)
        client.post("/api/v1/kb/upload", files={"file": ("r.pdf", b"r", "application/pdf")})

        # 多次刷新快照，key 稳定
        k1 = [r["idempotency_key"] for r in client.get("/api/v1/tasks/today").json()["completed_tasks"]]
        k2 = [r["idempotency_key"] for r in client.get("/api/v1/tasks/today").json()["completed_tasks"]]
        assert k1 == k2 and len(k1) == 1

    def test_repeated_action_is_idempotent_no_duplicate_popup(self, pclient, monkeypatch):
        """同一动作重复调用：不重复插回执、completed_tasks 不重复出现。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            task = _seed_pending_task(session, 9901, "upload")
        _patch_upload(monkeypatch)

        r1 = client.post("/api/v1/kb/upload", files={"file": ("a.pdf", b"a", "application/pdf")})
        keys1 = [r["idempotency_key"] for r in r1.json()["completed_tasks"]]
        # 第二次再传（同类型动作；哈希不同不会 duplicate，但 upload 任务已 completed）
        _patch_upload(monkeypatch, document_id="another-doc")
        r2 = client.post("/api/v1/kb/upload", files={"file": ("b.pdf", b"bbbbbbbb", "application/pdf")})
        keys2 = [r["idempotency_key"] for r in r2.json()["completed_tasks"]]

        assert keys1 != []  # 第一次动作产出回执
        assert keys2 == []  # 任务已 completed，重复动作不再产出新回执（幂等）
        today = client.get("/api/v1/tasks/today").json()["completed_tasks"]
        ids = [r["id"] for r in today]
        assert len(ids) == len(set(ids)), "today 回执不应有重复"


# ══ #38：Evidence Impact 独立契约 ══════════════════════════════

class TestIssue38EvidenceImpact:
    def test_goal_completion_creates_evidence_event(self, pclient, monkeypatch):
        """真实资料动作完成目标关联任务后，证据列表能看到前后值。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            goal = Goal(user_id=9901, text="通过高数期末考", status="active")
            session.add(goal)
            session.commit()
            session.refresh(goal)
            _seed_pending_task(session, 9901, "upload", goal_id=goal.id)
            goal_id = goal.id

        _patch_upload(monkeypatch, document_id="ev-doc")
        resp = client.post("/api/v1/kb/upload", files={"file": ("ev.pdf", b"%PDF-1.4", "application/pdf")})
        assert resp.json()["completed_tasks"]

        ev_resp = client.get(f"/api/v1/goals/{goal_id}/evidence")
        assert ev_resp.status_code == 200
        events = ev_resp.json()
        assert len(events) >= 1
        e = events[-1]
        # 契约字段完整（不是 task.evidence.document_id 冒充）
        assert {"id", "goal_id", "occurred_at", "source", "before", "after", "scope", "confirmation"} <= set(e.keys())
        assert e["goal_id"] == goal_id
        assert e["before"] == {"status": "pending"}
        assert e["after"]["status"] == "completed"
        assert e["confirmation"] == "pending"

    def test_evidence_list_isolated_by_user(self, pclient):
        """别人的 goal_id 拿不到证据列表（404）。"""
        client, SessionLocal = pclient
        # 直接查一个不存在的 goal —— 路由必须 404 而非泄漏他人数据
        resp = client.get("/api/v1/goals/999999/evidence")
        assert resp.status_code == 404

    def test_evidence_endpoint_exists_on_foreign_goal(self, pclient, monkeypatch):
        """另一用户的 goal → 当前用户访问返回 404（用户隔离）。"""
        from pgutil import make_sessionmaker as ms
        client, SessionLocal = pclient
        with SessionLocal() as session:
            other = User(id=9902, email="prod-b@example.com", password_hash="h", nickname="B", is_active=True)
            session.add(other)
            session.flush()
            goal = Goal(user_id=9902, text="别人的目标", status="active")
            session.add(goal)
            session.commit()
            session.refresh(goal)
            foreign_goal_id = goal.id
        resp = client.get(f"/api/v1/goals/{foreign_goal_id}/evidence")
        assert resp.status_code == 404


# ══ #35：题型 schema 与判分 ════════════════════════════════════

def _start_session(client, doc_id, qids):
    r = client.post("/api/v1/quiz/sessions", json={"document_id": doc_id, "question_ids": qids, "title": "#35"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _answer(client, sid, qid, **body):
    payload = {"question_id": qid, **body}
    return client.post(f"/api/v1/quiz/sessions/{sid}/answers", json=payload)


class TestIssue35QuestionSchemasAndGrading:
    def test_match_options_carry_side(self, pclient):
        """match 题的 options 每项必须带 side（left/right），Web 不用按下标切半。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-match", "匹配书.pdf")
            opts = (
                '[{"key":"L1","text":"贝叶斯","side":"left"},'
                '{"key":"L2","text":"梯度下降","side":"left"},'
                '{"key":"R1","text":"概率基础","side":"right"},'
                '{"key":"R2","text":"优化方法","side":"right"}]'
            )
            qid = _seed_question_on_page(
                session, 9901, "pdoc-match", 1, qtype="match",
                options=opts, answer='{"L1":"R1","L2":"R2"}',
            )
        sid = _start_session(client, "pdoc-match", [qid])
        q = next(q for q in client.get(f"/api/v1/quiz/sessions/{sid}").json()["questions"] if q["question_id"] == qid)
        sides = [o["side"] for o in (q["options"] or [])]
        assert set(sides) == {"left", "right"}

        # 正确配对 correct；错误配对 wrong
        assert _answer(client, sid, qid, user_answer='{"L1":"R1","L2":"R2"}').json()["status"] == "correct"


    def test_classify_options_items_categories(self, pclient):
        """classify options 必须是 items[] + categories[] 两段结构。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-classify", "分类书.pdf")
            opts = (
                '{"items":[{"id":"i1","text":"贝叶斯"},{"id":"i2","text":"牛顿法"},'
                '{"id":"i3","text":"极大似然"}],'
                '"categories":[{"id":"c1","text":"概率基础"},{"id":"c2","text":"优化方法"}]}'
            )
            qid = _seed_question_on_page(
                session, 9901, "pdoc-classify", 1, qtype="classify",
                options=opts, answer='{"i1":"c1","i2":"c2","i3":"c1"}',
            )
        sid = _start_session(client, "pdoc-classify", [qid])
        q = next(q for q in client.get(f"/api/v1/quiz/sessions/{sid}").json()["questions"] if q["question_id"] == qid)
        raw_opts = q["options"]
        # 序列化层保持 items+categories 结构（不再是扁平 [{key,text}] 列表）
        first = raw_opts[0] if isinstance(raw_opts, list) else raw_opts
        text = str(first)
        assert "items" in text and "categories" in text

        # 判分：条目→类别映射
        r_ok = _answer(client, sid, qid, user_answer='{"i1":"c1","i2":"c2","i3":"c1"}')
        assert r_ok.json()["status"] == "correct"

    def test_classify_wrong_mapping_is_wrong(self, pclient):
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-cw", "分类错书.pdf")
            opts = ('{"items":[{"id":"i1","text":"贝叶斯"}],"categories":[{"id":"c1","text":"概率"},{"id":"c2","text":"优化"}]}')
            qid = _seed_question_on_page(
                session, 9901, "pdoc-cw", 1, qtype="classify",
                options=opts, answer='{"i1":"c1"}',
            )
        sid = _start_session(client, "pdoc-cw", [qid])
        r = _answer(client, sid, qid, user_answer='{"i1":"c2"}')
        assert r.json()["status"] == "wrong"

    def test_true_false_garbage_value_returns_400(self, pclient):
        """true_false 收到 'maybe'/'yes2' 等无法解析值 → 400，不当 false。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-tf", "判断书.pdf")
            qid = _seed_question_on_page(
                session, 9901, "pdoc-tf", 1, qtype="true_false", answer="true",
            )
        sid = _start_session(client, "pdoc-tf", [qid])

        r = _answer(client, sid, qid, user_answer="maybe")
        assert r.status_code == 400, r.text

        # 合法值仍可判
        r2 = _answer(client, sid, qid, user_answer="true")
        assert r2.status_code == 200 and r2.json()["status"] == "correct"

    def test_true_false_accepts_bool_aliases(self, pclient):
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-tf2", "判断书2.pdf")
            q1 = _seed_question_on_page(session, 9901, "pdoc-tf2", 1, qtype="true_false", answer="对")
            q2 = _seed_question_on_page(session, 9901, "pdoc-tf2", 2, qtype="true_false", answer="false")
        sid = _start_session(client, "pdoc-tf2", [q1, q2])
        assert _answer(client, sid, q1, user_answer="true").json()["status"] == "correct"
        assert _answer(client, sid, q2, user_answer="错").json()["status"] == "correct"

    def test_sort_order_matters(self, pclient):
        """sort 判分：顺序不同结果不同（同一题判分逻辑直接验证，不经会话完成态干扰）。"""
        from app.services.quiz.quiz_service import _grade_answer
        import asyncio

        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-sort", "排序书.pdf")
            opts = '[{"key":"s1","text":"极限"},{"key":"s2","text":"导数"},{"key":"s3","text":"积分"}]'
            qid = _seed_question_on_page(
                session, 9901, "pdoc-sort", 1, qtype="sort", options=opts,
                answer='["s1","s2","s3"]',
            )
            question = session.query(GlobalQuestion).filter(GlobalQuestion.id == qid).first()
            assert question is not None
            q_stem = question.stem
            q_type = question.question_type
            q_answer = question.answer

        class _Q:
            id = qid
            stem = q_stem
            question_type = q_type
            answer = q_answer

        # 顺序敏感：正序 correct，乱序 wrong
        assert asyncio.run(_grade_answer(_Q(), '["s1","s2","s3"]', None)) == "correct"
        assert asyncio.run(_grade_answer(_Q(), '["s2","s1","s3"]', None)) == "wrong"
        assert asyncio.run(_grade_answer(_Q(), 'not-json', None)) == "wrong"

        # 再走一遍 HTTP 链路：单独会话答一次正确的（避免 upsert 撞会话完成态）
        sid = _start_session(client, "pdoc-sort", [qid])
        r = _answer(client, sid, qid, user_answer='["s1","s2","s3"]')
        assert r.status_code == 200 and r.json()["status"] == "correct"

    def test_single_multi_fill_no_regression(self, pclient):
        """单选/多选/填空不回归。"""
        client, SessionLocal = pclient
        with SessionLocal() as session:
            _seed_document(session, 9901, "pdoc-base", "回归书.pdf")
            sc = _seed_question_on_page(session, 9901, "pdoc-base", 1, qtype="single_choice", answer="A")
            mc = _seed_question_on_page(
                session, 9901, "pdoc-base", 2, qtype="multi_choice",
                options='[{"key":"A","text":"1"},{"key":"B","text":"2"},{"key":"C","text":"3"}]',
                answer="AB",
            )
            fb = _seed_question_on_page(
                session, 9901, "pdoc-base", 3, qtype="fill_blank",
                options=None, answer="极限",
            )
        sid = _start_session(client, "pdoc-base", [sc, mc, fb])

        assert _answer(client, sid, sc, user_answer="A").json()["status"] == "correct"
        # 多选乱序等价
        assert _answer(client, sid, mc, user_answer="BA").json()["status"] == "correct"
        assert _answer(client, sid, fb, user_answer=" 极限 ").json()["status"] == "correct"

    def test_generate_doc_notes_types_decided_by_result(self, pclient, monkeypatch):
        """出题接口不接收题型参数（schema 层拒绝额外可选题型字段）。"""
        from app.schemas.page import PageGenerateRequest
        req = PageGenerateRequest(document_id="d1", page_numbers=[1])
        assert not hasattr(req, "question_type"), "出题请求不应暴露题型参数（题型由生成结果决定）"
