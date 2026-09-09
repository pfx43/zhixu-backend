"""任务 Agent / 缺口候选人：缺页才出题，做完不再派同一页。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pgutil import make_sessionmaker
from app.models import (
    User,
    KbCollection,
    Document,
    DocumentSegment,
    GlobalQuestion,
    QuestionProvenance,
    UserQuestionRef,
    DailyTask,
)
from app.services.tasks import task_service
from app.services.tasks.candidates import collect_task_candidates, fallback_assign
from app.services.tools.task_assign_tools import TaskAssignTools


def _seed_user(session, user_id=8801):
    session.add(
        User(
            id=user_id,
            email=f"u{user_id}@example.com",
            password_hash="hashed",
            nickname="T",
            is_active=True,
        )
    )
    session.commit()


def _seed_doc(session, user_id=8801, doc_id="doc-1", name="官方示例.md", pages=(1, 3)):
    session.add(
        KbCollection(
            id=f"coll-{doc_id}",
            user_id=user_id,
            name="学习区",
            zone="study",
            is_default=True,
        )
    )
    session.flush()
    session.add(
        Document(
            id=doc_id,
            user_id=user_id,
            collection_id=f"coll-{doc_id}",
            display_name=name,
            zone="study",
            content_hash=f"hash-{doc_id}",
            parsed_cache_key=f"parsed-{doc_id}",
            indexing_status="completed",
            segment_status="completed",
            question_gen_status="not_started",
        )
    )
    session.add(
        DocumentSegment(
            id=f"seg-{doc_id}",
            document_id=doc_id,
            order_index=0,
            title="第一章",
            content="内容",
            char_start=0,
            char_end=10,
            page_start=pages[0],
            page_end=pages[1],
        )
    )
    session.commit()


def _seed_question(session, user_id, doc_id, page):
    qid = f"q-{doc_id}-p{page}"
    session.add(
        GlobalQuestion(
            id=qid,
            content_hash=f"h-{qid}",
            stem=f"第 {page} 页的题",
            question_type="single_choice",
            options='[{"key":"A","text":"对"}]',
            answer="A",
            explanation="e",
            source_type="generated",
            tags='["极限"]',
        )
    )
    session.flush()
    session.add(
        QuestionProvenance(
            id=f"prov-{qid}",
            question_id=qid,
            document_id=doc_id,
            page_number=page,
        )
    )
    session.add(
        UserQuestionRef(
            id=f"ref-{qid}",
            user_id=user_id,
            question_id=qid,
            document_id=doc_id,
        )
    )
    session.commit()
    return qid


@pytest.fixture()
def db_session():
    engine, SessionLocal = make_sessionmaker()
    with SessionLocal() as session:
        _seed_user(session)
        yield session
    engine.dispose()


def test_candidates_generate_only_missing_pages(db_session):
    _seed_doc(db_session)
    _seed_question(db_session, 8801, "doc-1", 1)
    cands = collect_task_candidates(db_session, 8801)
    gen = [c for c in cands if c["task_type"] == "generate_questions"]
    assert len(gen) == 1
    assert set(gen[0]["payload"]["page_numbers"]) == {2, 3}
    assert 1 not in gen[0]["payload"]["page_numbers"]


def test_candidates_no_generate_when_all_pages_have_questions(db_session):
    _seed_doc(db_session)
    for p in (1, 2, 3):
        _seed_question(db_session, 8801, "doc-1", p)
    cands = collect_task_candidates(db_session, 8801)
    assert not any(c["task_type"] == "generate_questions" for c in cands)
    quiz = [c for c in cands if c["task_type"] == "practice"]
    assert quiz
    assert set(quiz[0]["payload"]["question_ids"]) == {
        "q-doc-1-p1",
        "q-doc-1-p2",
        "q-doc-1-p3",
    }


def test_ensure_does_not_repeat_generate_after_pages_filled(db_session):
    _seed_doc(db_session)
    for p in (1, 2, 3):
        _seed_question(db_session, 8801, "doc-1", p)
    first = task_service.ensure_today_tasks(db_session, 8801)
    assert not any(t.task_type == "generate_questions" for t in first)
    practice = [t for t in first if t.task_type == "practice"]
    assert practice
    practice[0].status = "completed"
    db_session.commit()
    again = task_service.ensure_today_tasks(db_session, 8801)
    assert not any(t.task_type == "generate_questions" for t in again)


def test_assign_task_rejects_unknown_candidate(db_session):
    _seed_doc(db_session)
    cands = collect_task_candidates(db_session, 8801)
    tools = TaskAssignTools(8801, cands, db_session)
    msg = tools.assign_task("gen-not-real", "出题", "因为目标")
    assert "没有这个候选人" in msg
    assert db_session.query(DailyTask).count() == 0


def test_assign_task_writes_title_reason_from_agent(db_session):
    _seed_doc(db_session)
    cands = collect_task_candidates(db_session, 8801)
    tools = TaskAssignTools(8801, cands, db_session)
    gen_id = [c["id"] for c in cands if c["task_type"] == "generate_questions"][0]
    msg = tools.assign_task(gen_id, "先给示例前两页出题", "目标要用这本书，这几页还没题", 2)
    assert "已布置" in msg
    row = db_session.query(DailyTask).one()
    assert row.title == "先给示例前两页出题"
    assert "还没题" in row.reason
    assert len(row.payload["page_numbers"]) == 2


def test_fallback_assign_not_same_pages_twice(db_session):
    _seed_doc(db_session)
    first = fallback_assign(db_session, 8801)
    assert first and first[0].task_type == "generate_questions"
    second = fallback_assign(db_session, 8801)
    assert second == []
