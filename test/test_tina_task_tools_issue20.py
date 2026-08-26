"""Issue #20 Tina 派任务工具 — 测试覆盖

验收条件（来自 Issue #20）：
1. 无 active 目标时，不能编造目标 id 改别人数据。
2. 检索 / toc / 出题返回或使用的页码来自入库字段，不是模型编的（禁止猜页）。
3. 布置的任务出现在 GET /tasks/today（与对话里「另一套任务」不一致的情况不存在）。
4. 主对话工具列表不含出题内部 submit_question。
5. 用户 A 的工具调不到用户 B 的书和题。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from app.models import User, Goal, KbCollection, Document, DocumentSegment, QuestionProvenance, GlobalQuestion, UserQuestionRef
from app.services.quiz import question_gen_service
from app.services.tools.task_tools import TaskPlannerTools, build_user_context
from app.services.tasks import task_service


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


def _seed_document(session, user_id: int, doc_id: str, name: str, with_segment=True):
    coll = KbCollection(id=f"coll-{doc_id}", user_id=user_id, name="学习区", zone="study", is_default=True)
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
    session.flush()
    if with_segment:
        session.add(DocumentSegment(
            id=f"seg-{doc_id}",
            document_id=doc_id,
            order_index=0,
            title="第一章",
            content="内容",
            char_start=0,
            char_end=10,
            page_start=1,
            page_end=3,
        ))
    session.commit()
    return doc


def _seed_question_on_page(session, user_id: int, doc_id: str, page: int):
    q = GlobalQuestion(
        id=f"q-{doc_id}-p{page}",
        content_hash=f"h-{doc_id}-p{page}",
        stem=f"第 {page} 页的题",
        question_type="single_choice",
        options='[{"key":"A","text":"对"},{"key":"B","text":"错"}]',
        answer="A",
        explanation="解析",
        source_type="generated",
    )
    session.add(q)
    session.flush()
    session.add(QuestionProvenance(
        id=f"prov-{doc_id}-p{page}", question_id=q.id, document_id=doc_id, page_number=page,
    ))
    session.add(UserQuestionRef(
        id=f"ref-{doc_id}-p{page}", user_id=user_id, question_id=q.id, document_id=doc_id,
    ))
    session.commit()


@pytest.fixture()
def task_tools_env():
    """构造 A(8801)/B(8802) 两用户 + 各自文档的独立测试库。"""
    engine, SessionLocal = _create_temp_db()
    with SessionLocal() as s:
        _seed_user(s, 8801, "a@example.com")
        _seed_user(s, 8802, "b@example.com")
        _seed_document(s, 8801, "doc-a", "A 的书.pdf")
        _seed_document(s, 8802, "doc-b", "B 的书.pdf")
        _seed_question_on_page(s, 8801, "doc-a", 2)
    yield SessionLocal
    engine.dispose()


def _tools_a():
    return TaskPlannerTools(user_id=8801)


def _tools_b():
    return TaskPlannerTools(user_id=8802)


def _tool_names(tools: TaskPlannerTools):
    names = tools.tools.tools_names
    if callable(names):
        names = names()
    return set(names)


# ── 验收 5：用户隔离 ─────────────────────────────────────────

def test_document_isolation(task_tools_env):
    """用户 A 的工具调不到用户 B 的书。"""
    tools_b = _tools_b()
    resp = json.loads(tools_b.get_document_toc("doc-a"))
    assert resp.get("error") and "无权访问" in resp["error"]

    resp_own = json.loads(tools_b.get_document_toc("doc-b"))
    assert resp_own["document_id"] == "doc-b"


def test_learning_gaps_only_own_data(task_tools_env):
    """缺口统计只反映自己的书。"""
    gaps_a = json.loads(_tools_a().get_learning_gaps())
    docs_a = {d["document_id"] for d in gaps_a["documents"]}
    assert docs_a == {"doc-a"}
    assert gaps_a["documents"][0]["question_count"] == 1  # A 在 doc-a 第 2 页有题

    gaps_b = json.loads(_tools_b().get_learning_gaps())
    docs_b = {d["document_id"] for d in gaps_b["documents"]}
    assert docs_b == {"doc-b"}


def test_goal_isolation(task_tools_env):
    """B 的 revise_goal 不会改到 A 的目标；A 无目标时 B 读不到。"""
    # A 先写一条 active goal
    r = json.loads(_tools_a().revise_goal("研究生上岸"))
    assert r["status"] == "ok"

    # B 读到的是 null（看不到 A 的目标）
    r_b = json.loads(_tools_b().get_active_goal())
    assert r_b["goal"] is None

    # B 写自己的目标
    r_b2 = json.loads(_tools_b().revise_goal("考公上岸"))
    assert r_b2["status"] == "ok"

    # A 的目标没被 B 覆盖
    r_a = json.loads(_tools_a().get_active_goal())
    assert r_a["goal"]["text"] == "研究生上岸"


# ── 验收 2：禁止猜页 ─────────────────────────────────────────

async def _fake_generate_from_pages(**kwargs):
    from app.schemas.question import PageQuestionResponse
    return PageQuestionResponse(
        document_id=kwargs.get("document_id"),
        page_numbers=list(kwargs.get("page_numbers") or []),
        mode="generate",
        questions_created=1,
        questions_reused=0,
        total_questions=len(kwargs.get("page_numbers") or []),
    )


def test_generate_questions_rejects_guessed_pages(task_tools_env, monkeypatch):
    """越界页码（不在目录/入库分段范围）被拒绝，并返回合法页码。

    工具是 async def，这里用 asyncio.run 跑；CI 不装 pytest-asyncio，函数保持同步。
    """
    import asyncio

    monkeypatch.setattr(question_gen_service, "is_question_gen_async", lambda: False)
    monkeypatch.setattr(question_gen_service, "generate_from_pages", _fake_generate_from_pages)

    resp = json.loads(asyncio.run(_tools_a().generate_questions("doc-a", "99")))
    assert "error" in resp
    assert "禁止手填" in resp["error"]
    assert 1 in resp["valid_pages"]  # 合法页来自分段 page_start=1


def test_generate_questions_accepts_toc_pages(task_tools_env, monkeypatch):
    """页码来自目录/入库分段（合法）时正常调用现有按页出题。"""
    import asyncio

    called = {}

    async def fake_generate(**kwargs):
        called.update(kwargs)
        return await _fake_generate_from_pages(**kwargs)

    monkeypatch.setattr(question_gen_service, "is_question_gen_async", lambda: False)
    monkeypatch.setattr(question_gen_service, "generate_from_pages", fake_generate)

    resp = json.loads(asyncio.run(_tools_a().generate_questions("doc-a", "1,2")))
    assert resp["status"] == "completed"
    assert called["user_id"] == 8801
    assert called["page_numbers"] == [1, 2]


# ── 验收 4：不暴露 submit_question ───────────────────────────

def test_tools_do_not_expose_submit_question():
    names = _tool_names(_tools_a())
    # tina Tools(name="task_planner") 会给工具名加命名空间前缀
    assert not any("submit_question" in n for n in names)
    assert not any("get_near_page" in n for n in names)
    expected_suffixes = {
        "get_active_goal",
        "revise_goal",
        "get_document_toc",
        "generate_questions",
        "get_learning_gaps",
        "ensure_today_tasks",
    }
    prefix = "task_planner_"
    suffixes = {n[len(prefix):] for n in names if n.startswith(prefix)}
    assert expected_suffixes <= suffixes


# ── 验收 1 / 3：ensure 写入 daily_tasks，与 GET /tasks/today 一致 ──

def test_ensure_today_tasks_writes_daily_tasks(task_tools_env):
    """B 有书没题 → ensure 布置按页出题任务；任务落在 daily_tasks（与 tasks/today 同一张表）。"""
    resp = json.loads(_tools_b().ensure_today_tasks())
    assert resp["status"] == "ok"
    assert len(resp["tasks"]) >= 1
    gen_tasks = [t for t in resp["tasks"] if t["task_type"] == "generate_questions"]
    assert gen_tasks, "有书没题的用户应派按页出题任务"

    # 与 GET /api/v1/tasks/today 数据同源：同一张 daily_tasks
    from app.crud import task as task_crud
    with task_tools_env() as db:
        db_tasks = task_crud.list_tasks(db, 8802, task_service.today_local())
        assert len(db_tasks) == len(resp["tasks"])
        assert {t.id for t in db_tasks} == {t["id"] for t in resp["tasks"]}

    # 再 ensure 不重复派
    resp2 = json.loads(_tools_b().ensure_today_tasks())
    assert [t["id"] for t in resp2["tasks"]] == [t["id"] for t in resp["tasks"]]


def test_ensure_today_tasks_generates_practice_when_questions_exist(task_tools_env):
    """A 有书有题 → 派刷题任务。"""
    resp = json.loads(_tools_a().ensure_today_tasks())
    practice_tasks = [t for t in resp["tasks"] if t["task_type"] == "practice"]
    assert practice_tasks


# ── 验收 1：无 active 目标不能编造 id 改数据 ─────────────────

def test_get_active_goal_null_when_none(task_tools_env):
    resp = json.loads(_tools_a().get_active_goal())
    assert resp["goal"] is None


def test_revise_goal_with_attributes(task_tools_env):
    resp = json.loads(_tools_a().revise_goal("考研上岸 408", '{"subject":"计算机"}'))
    assert resp["status"] == "ok"
    with task_tools_env() as db:
        goal = db.query(Goal).filter(Goal.user_id == 8801, Goal.status == "active").first()
        assert goal.text == "考研上岸 408"
        assert goal.attributes == {"subject": "计算机"}


# ── 上下文注入：资料列表 / 目标 / 今日任务 ────────────────────

def test_build_user_context_includes_state(task_tools_env):
    with task_tools_env() as db:
        task = task_service.ensure_today_tasks(db, 8801)
        db.commit()
    context = build_user_context(8801)
    assert "A 的书.pdf" in context
    assert "资料列表" in context
    assert "当前目标" in context
    assert "今日任务" in context
