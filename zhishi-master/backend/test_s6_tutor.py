"""
S6 辅导会话验证 — mock Agent，不依赖 HTTP / Tina
运行: cd backend && python test_s6_tutor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud import kb as kb_crud
from app.models import User
from app.schemas.quiz import QuizSessionCreate
from app.schemas.tutor import TutorSessionCreate
from app.services.question_gen_service import generate_questions
from app.services.quiz_service import create_quiz_session, submit_answer
from app.services.segment_service import segment_document
from app.services import tutor_service
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


def _mock_tutor_agent(system_prompt, message, history=None, *, stream=False):
  if stream:
    def _gen():
      yield {"role": "assistant", "content": f"引导思考：{message[:20]}"}
    return _gen()
  return f"引导思考：{message[:20]}"


def _setup_user_with_questions(db, num_segments=3):
    user = User(
        email="s6@test.local",
        password_hash="x",
        username="s6user",
        nickname="S6",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()

    md = "# 导论\n学习资料内容。\n\n## 要点\n重点内容。\n\n## 总结\n总结内容。"
    parsed_path = storage_service.save_global_parsed("hash_s6_test", md)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_s6_test",
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
        content_hash="hash_s6_test",
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


def _reset_tutor_history():
    tutor_service._in_memory_history.clear()


def test_create_session_binds_segment_context():
    _reset_tutor_history()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    quiz = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()
    qid = quiz.questions[0].question_id

    session = tutor_service.create_tutor_session(
        db,
        user.id,
        TutorSessionCreate(question_id=qid, quiz_session_id=quiz.id),
    )
    db.commit()

    assert session.question_id == qid
    assert session.segment_id is not None
    assert session.document_id == doc.id
    assert session.segment_context.snippet
    assert session.messages == []

    from app.crud import tutor as tutor_crud

    row = tutor_crud.get_session(db, session.id, user.id)
    history = tutor_service._load_history(user.id, row.chat_session_id)
    assert any(m["role"] == "system" for m in history)
    assert "导论" in history[0]["content"] or "要点" in history[0]["content"]

    print("OK create_session_binds_segment_context")
    db.close()


def test_create_session_after_unknown():
    _reset_tutor_history()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    quiz = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()
    qid = quiz.questions[0].question_id
    submit_answer(
        db,
        user.id,
        quiz.id,
        question_id=qid,
        user_answer=None,
        status_hint="unknown",
    )
    db.commit()

    session = tutor_service.create_tutor_session(
        db,
        user.id,
        TutorSessionCreate(question_id=qid, quiz_session_id=quiz.id),
    )
    db.commit()

    from app.crud import tutor as tutor_crud

    row = tutor_crud.get_session(db, session.id, user.id)
    history = tutor_service._load_history(user.id, row.chat_session_id)
    system_msg = next(m for m in history if m["role"] == "system")
    assert "我不会" in system_msg["content"]

    print("OK create_session_after_unknown")
    db.close()


def test_message_roundtrip_mock_agent():
    _reset_tutor_history()
    tutor_service._call_tutor_agent = _mock_tutor_agent

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    quiz = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()
    qid = quiz.questions[0].question_id

    session = tutor_service.create_tutor_session(
        db,
        user.id,
        TutorSessionCreate(question_id=qid, quiz_session_id=quiz.id),
    )
    db.commit()

    reply = tutor_service.send_tutor_message(
        db, user.id, session.id, "这道题我不太理解选项 B"
    )
    db.commit()

    assert reply.role == "assistant"
    assert "引导思考" in reply.content

    loaded = tutor_service.get_tutor_session(db, user.id, session.id)
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"

    print("OK message_roundtrip_mock_agent")
    db.close()


def test_segment_id_matches_quiz_citation():
    _reset_tutor_history()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    quiz = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()
    qid = quiz.questions[0].question_id
    result = submit_answer(
        db, user.id, quiz.id, question_id=qid, user_answer="B"
    )
    db.commit()

    session = tutor_service.create_tutor_session(
        db,
        user.id,
        TutorSessionCreate(question_id=qid, quiz_session_id=quiz.id),
    )
    db.commit()

    assert result.citation is not None
    assert session.segment_id == result.citation.segment_id

    print("OK segment_id_matches_quiz_citation")
    db.close()


def test_system_prompt_injects_segment_content():
    _reset_tutor_history()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_user_with_questions(db)
    quiz = create_quiz_session(
        db, user.id, QuizSessionCreate(document_id=doc.id)
    )
    db.commit()
    qid = quiz.questions[0].question_id

    session = tutor_service.create_tutor_session(
        db,
        user.id,
        TutorSessionCreate(question_id=qid, quiz_session_id=quiz.id),
    )
    db.commit()

    from app.crud import tutor as tutor_crud

    row = tutor_crud.get_session(db, session.id, user.id)
    history = tutor_service._load_history(user.id, row.chat_session_id)
    system_msg = next(m for m in history if m["role"] == "system")

    assert "苏格拉底" in system_msg["content"]
    assert "禁止直接给出" in system_msg["content"]
    assert qid[:8] not in system_msg["content"]  # stem text present instead
    assert "核心内容" in system_msg["content"] or "关于" in system_msg["content"]

    print("OK system_prompt_injects_segment_content")
    db.close()


if __name__ == "__main__":
    test_create_session_binds_segment_context()
    test_create_session_after_unknown()
    test_message_roundtrip_mock_agent()
    test_segment_id_matches_quiz_citation()
    test_system_prompt_injects_segment_content()
    print("\nAll S6 checks passed.")
