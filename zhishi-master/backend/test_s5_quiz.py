"""
S5 刷题会话验证 — mock 题目与会话，不依赖 HTTP
运行: cd backend && python test_s5_quiz.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fastapi import HTTPException

from app.core.database import Base
from app.crud import kb as kb_crud
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.models import QuizAnswer, User
from app.schemas.quiz import QuizSessionCreate
from app.services.question_gen_service import generate_questions
from app.services.quiz_service import (
    create_quiz_session,
    get_quiz_session,
    get_session_results,
    submit_answer,
)
from app.services.segment_service import segment_document
from app.services.storage_service import storage_service


def _mock_provider(segment):
    title = segment.title or "默认"
    return [
        {
            "stem": f"关于「{title}」的核心内容，以下哪项正确？",
            "options": [
                {"key": "A", "text": "选项 A"},
                {"key": "B", "text": "选项 B"},
                {"key": "C", "text": "选项 C"},
                {"key": "D", "text": "选项 D"},
            ],
            "answer": "A",
            "explanation": "测试解析内容",
            "tags": ["测试"],
        }
    ]


def _setup_user_with_questions(db, num_segments=3):
    user = User(
        email="s5@test.local",
        password_hash="x",
        username="s5user",
        nickname="S5",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()

    md = "# 导论\n学习资料内容。\n\n## 要点\n重点内容。\n\n## 总结\n总结内容。"
    parsed_path = storage_service.save_global_parsed("hash_s5_test", md)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_s5_test",
        original_filename="notes.md",
        file_size=len(md.encode()),
        storage_path="/tmp/notes.md",
        parsed_text_path=parsed_path,
    )
    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=cols[0].id,
        zone="study",
        display_name="notes.md",
        content_hash="hash_s5_test",
        global_document_id=global_doc.id,
        parsed_cache_key=parsed_path,
    )
    db.commit()
    segment_document(doc.id, db)
    db.commit()
    db.refresh(doc)

    generate_questions(db, user.id, document_id=doc.id, provider=_mock_provider)
    db.commit()
    db.refresh(doc)

    return user, doc


def test_create_session_from_document():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db,
        user.id,
        QuizSessionCreate(document_id=doc.id),
    )
    db.commit()

    assert session.total_questions >= 1
    assert session.answered_count == 0
    assert session.status == "active"
    assert all(q.stem for q in session.questions)
    assert all(q.options for q in session.questions)

    print("OK create_session_from_document")
    db.close()


def test_submit_correct_answer():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()

    qid = session.questions[0].question_id
    result = submit_answer(
        db, user.id, session.id, question_id=qid, user_answer="A"
    )
    db.commit()

    assert result.status == "correct"
    assert result.explanation is None
    assert result.citation is None
    assert result.answered_count == 1

    print("OK submit_correct_answer")
    db.close()


def test_submit_wrong_returns_explanation_and_citation():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()

    qid = session.questions[0].question_id
    result = submit_answer(
        db, user.id, session.id, question_id=qid, user_answer="B"
    )
    db.commit()

    assert result.status == "wrong"
    assert result.explanation == "测试解析内容"
    assert result.citation is not None
    assert result.citation.segment_id is not None
    assert result.citation.snippet

    print("OK submit_wrong_returns_explanation_and_citation")
    db.close()


def test_submit_unknown_status():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()

    qid = session.questions[0].question_id
    result = submit_answer(
        db,
        user.id,
        session.id,
        question_id=qid,
        user_answer=None,
        status_hint="unknown",
    )
    db.commit()

    assert result.status == "unknown"
    assert result.explanation == "测试解析内容"
    assert result.citation is not None
    assert result.citation.segment_id is not None

    answer_row = quiz_crud.get_answer(db, session.id, qid)
    assert answer_row.status == "unknown"

    print("OK submit_unknown_status")
    db.close()


def test_session_completes_after_all_answered():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()

    for i, q in enumerate(session.questions):
        submit_answer(
            db,
            user.id,
            session.id,
            question_id=q.question_id,
            user_answer="A" if i == 0 else "B",
            status_hint="unknown" if i == len(session.questions) - 1 else None,
        )
    db.commit()

    updated = get_quiz_session(db, user.id, session.id)
    assert updated.status == "completed"
    assert updated.answered_count == updated.total_questions
    assert updated.finished_at is not None

    results = get_session_results(db, user.id, session.id)
    assert results.wrong_count >= 1
    assert results.unknown_count >= 1
    assert len(results.items) >= 2
    assert all(item.citation and item.citation.segment_id for item in results.items)

    print("OK session_completes_after_all_answered")
    db.close()


def test_create_session_no_questions_409():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s5empty@test.local",
        password_hash="x",
        username="s5empty",
        nickname="S5Empty",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=cols[0].id,
        zone="study",
        display_name="empty.md",
        content_hash="empty_s5",
    )
    doc.question_gen_status = "not_started"
    db.commit()

    try:
        create_quiz_session(
            db, user.id, QuizSessionCreate(document_id=doc.id)
        )
        assert False, "should raise"
    except HTTPException as e:
        assert e.status_code == 409

    print("OK create_session_no_questions_409")
    db.close()


def test_answer_upsert_on_retry():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    session = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()

    qid = session.questions[0].question_id
    submit_answer(db, user.id, session.id, question_id=qid, user_answer="B")
    submit_answer(db, user.id, session.id, question_id=qid, user_answer="A")
    db.commit()

    answers = db.query(QuizAnswer).filter(QuizAnswer.session_id == session.id).all()
    assert len(answers) == 1
    assert answers[0].status == "correct"

    print("OK answer_upsert_on_retry")
    db.close()


if __name__ == "__main__":
    test_create_session_from_document()
    test_submit_correct_answer()
    test_submit_wrong_returns_explanation_and_citation()
    test_submit_unknown_status()
    test_session_completes_after_all_answered()
    test_create_session_no_questions_409()
    test_answer_upsert_on_retry()
    print("\nAll S5 checks passed.")
