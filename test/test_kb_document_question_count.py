"""资料列表应返回当前用户在该文档上的题目数，供前端显示「可刷题」而不是「未出题」。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import User, KbCollection, Document
from app.crud import question as question_crud
from app.services.knowledge import kb_service
from app.services.quiz import question_gen_service
from pgutil import make_sessionmaker


@pytest.fixture()
def db_session():
    engine, SessionLocal = make_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_user(db, email: str) -> User:
    user = User(email=email, password_hash="hash", nickname="用户", is_active=True)
    db.add(user)
    db.flush()
    return user


def _make_doc(db, user: User, name: str) -> Document:
    collection = KbCollection(user_id=user.id, name=f"collection-{name}", zone="study")
    db.add(collection)
    db.flush()
    doc = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name=name,
        zone="study",
        content_hash=f"hash-{name}-{user.id}",
        indexing_status="completed",
        question_gen_status="not_started",
    )
    db.add(doc)
    db.flush()
    return doc


def _page(page_number: int) -> dict:
    return {
        "page_number": page_number,
        "title": f"第 {page_number} 页",
        "content": f"第 {page_number} 页的正文内容。",
        "char_start": 0,
        "char_end": 100,
        "segment_id": None,
    }


def _qdata(stem: str) -> dict:
    return {
        "stem": stem,
        "question_type": "single_choice",
        "options": [
            {"key": "A", "text": "选项 A"},
            {"key": "B", "text": "选项 B"},
            {"key": "C", "text": "选项 C"},
            {"key": "D", "text": "选项 D"},
        ],
        "answer": "A",
        "explanation": "解析",
        "tags": ["测试"],
    }


def test_list_documents_question_count_reflects_user_refs(db_session):
    user = _make_user(db_session, "kb-qcount@example.com")
    doc_with = _make_doc(db_session, user, "官方示例.md")
    doc_empty = _make_doc(db_session, user, "还没出题.md")

    question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc_with,
        page=_page(1),
        qdata=_qdata("已经出过的题？"),
        source_type="generated",
    )
    db_session.commit()

    listed = kb_service.list_documents(db_session, user.id, None)
    by_id = {item.id: item for item in listed.documents}

    assert by_id[doc_with.id].question_count == 1
    assert by_id[doc_empty.id].question_count == 0


def test_list_documents_clears_stale_processing_when_questions_exist(db_session):
    user = _make_user(db_session, "kb-qcount-stale@example.com")
    doc = _make_doc(db_session, user, "卡住的出题.md")
    doc.question_gen_status = "processing"
    question_gen_service._persist_question_from_page(
        db_session,
        user_id=user.id,
        document=doc,
        page=_page(1),
        qdata=_qdata("已经落库的题"),
        source_type="generated",
    )
    db_session.commit()

    listed = kb_service.list_documents(db_session, user.id, None)
    item = next(d for d in listed.documents if d.id == doc.id)
    assert item.question_gen_status == "completed"
    assert item.question_count == 1

    db_session.refresh(doc)
    assert doc.question_gen_status == "completed"


def test_list_documents_keeps_processing_while_generation_inflight(db_session):
    from app.services.quiz import qgen_job_service

    user = _make_user(db_session, "kb-qcount-inflight@example.com")
    doc = _make_doc(db_session, user, "正在出题.md")
    doc.question_gen_status = "processing"
    db_session.commit()

    qgen_job_service.mark_document_generating(doc.id)
    try:
        listed = kb_service.list_documents(db_session, user.id, None)
        item = next(d for d in listed.documents if d.id == doc.id)
        assert item.question_gen_status == "processing"
    finally:
        qgen_job_service.unmark_document_generating(doc.id)


def test_count_user_questions_for_documents_isolates_users(db_session):
    user_a = _make_user(db_session, "kb-qcount-a@example.com")
    user_b = _make_user(db_session, "kb-qcount-b@example.com")
    doc_a = _make_doc(db_session, user_a, "A的书.md")
    doc_b = _make_doc(db_session, user_b, "B的书.md")

    question_gen_service._persist_question_from_page(
        db_session,
        user_id=user_a.id,
        document=doc_a,
        page=_page(2),
        qdata=_qdata("只有 A 能看见"),
        source_type="generated",
    )
    db_session.commit()

    counts_a = question_crud.count_user_questions_for_documents(
        db_session, user_a.id, [doc_a.id, doc_b.id]
    )
    counts_b = question_crud.count_user_questions_for_documents(
        db_session, user_b.id, [doc_a.id, doc_b.id]
    )

    assert counts_a.get(doc_a.id) == 1
    assert counts_a.get(doc_b.id) is None
    assert counts_b == {}
