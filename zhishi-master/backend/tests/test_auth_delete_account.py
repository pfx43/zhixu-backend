import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base
from app.models import (
    User, KbCollection, Document, DocumentSegment,
    GlobalQuestion, GlobalDocument,
    QuestionProvenance, UserQuestionRef,
    QuizSession, QuizSessionQuestion, QuizAnswer,
    TutorSession, UserNote, TrainingPlan, QuestionTag, OnboardingState,
)
from app.services import auth_service
from app.services.auth_service import AuthManager


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_delete_account_basic(monkeypatch, db_session):
    """基础用例：User + KbCollection + Document + DocumentSegment"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    user = User(
        email="delete-me@example.com",
        password_hash="hash",
        username="delete-me",
        nickname="delete-me",
        is_active=True,
        dataset_id="dataset-1",
    )
    db_session.add(user)
    db_session.flush()

    collection = KbCollection(user_id=user.id, name="测试分区", zone="study")
    db_session.add(collection)
    db_session.flush()

    document = Document(
        user_id=user.id,
        collection_id=collection.id,
        display_name="测试文档",
        zone="study",
        content_hash="abc123",
    )
    db_session.add(document)
    db_session.flush()
    document_id = document.id

    segment = DocumentSegment(
        document_id=document.id,
        order_index=1,
        content="hello world",
        char_start=0,
        char_end=11,
    )
    db_session.add(segment)
    db_session.commit()

    result = AuthManager.delete_account(db_session, user.id)

    assert result["message"] == "账号已注销"
    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(KbCollection).filter(KbCollection.user_id == user.id).count() == 0
    assert db_session.query(Document).filter(Document.user_id == user.id).count() == 0
    assert db_session.query(DocumentSegment).filter(DocumentSegment.document_id == document_id).count() == 0


def test_delete_account_commit_failure_preserves_user_token_and_external_dataset(
    monkeypatch,
    db_session,
):
    """数据库回滚时不得提前销毁会话或删除外部知识库。"""
    user = User(
        email="rollback@example.com",
        password_hash="hash",
        nickname="rollback",
        is_active=True,
        dataset_id="dataset-rollback",
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    token = "rollback-token"
    auth_service.cache.set_session(token, {"user_id": user_id, "email": user.email})
    deleted_datasets = []
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", deleted_datasets.append)

    def fail_commit():
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    try:
        with pytest.raises(HTTPException) as exc_info:
            AuthManager.delete_account(db_session, user_id)

        assert exc_info.value.status_code == 500
        assert db_session.query(User).filter(User.id == user_id).first() is not None
        assert auth_service.cache.get_session(token) == {
            "user_id": user_id,
            "email": "rollback@example.com",
        }
        assert deleted_datasets == []
    finally:
        auth_service.cache.delete_key(f"auth:token:{token}")


def test_delete_account_with_quiz_linked_to_collection_prevents_relogin(
    monkeypatch,
    db_session,
):
    """注销必须先清理引用知识库分区的刷题会话，且原凭据不能再次登录。"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)
    monkeypatch.setattr(auth_service, "verify_password", lambda password, password_hash: True)
    monkeypatch.setattr(auth_service.cache, "set_session", lambda token, user_data, ttl: None)

    user = User(
        email="linked-quiz@example.com",
        password_hash="hash",
        nickname="linked-quiz",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    user_id = user.id

    collection = KbCollection(user_id=user_id, name="刷题分区", zone="study")
    db_session.add(collection)
    db_session.flush()
    collection_id = collection.id

    document = Document(
        user_id=user_id,
        collection_id=collection_id,
        display_name="刷题文档",
        zone="study",
        content_hash="linked-quiz-doc",
    )
    db_session.add(document)
    db_session.flush()
    document_id = document.id

    quiz_session = QuizSession(
        id="linked-quiz-session",
        user_id=user_id,
        collection_id=collection_id,
        document_id=document_id,
        status="in_progress",
    )
    db_session.add(quiz_session)
    db_session.commit()

    delete_error = None
    try:
        result = AuthManager.delete_account(db_session, user_id)
    except HTTPException as exc:
        delete_error = exc
        result = None

    with pytest.raises(HTTPException) as login_error:
        AuthManager.login(
            db=db_session,
            email="linked-quiz@example.com",
            password="original-password",
        )

    assert login_error.value.status_code == 401
    assert delete_error is None
    assert result == {"message": "账号已注销"}
    assert db_session.query(User).filter(User.id == user_id).first() is None
    assert db_session.query(QuizSession).filter(QuizSession.id == "linked-quiz-session").count() == 0
    assert db_session.query(Document).filter(Document.id == document_id).count() == 0
    assert db_session.query(KbCollection).filter(KbCollection.id == collection_id).count() == 0


def test_delete_account_with_question_provenance(monkeypatch, db_session):
    """验证 QuestionProvenance（FK → documents / document_segments）被正确先行清理"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    user = User(
        email="provenance-test@example.com",
        password_hash="hash",
        nickname="p-test",
        is_active=True,
        dataset_id="d-1",
    )
    db_session.add(user)
    db_session.flush()

    collection = KbCollection(user_id=user.id, name="分區", zone="study")
    db_session.add(collection)
    db_session.flush()

    doc = Document(user_id=user.id, collection_id=collection.id, display_name="doc", zone="study", content_hash="h1")
    db_session.add(doc)
    db_session.flush()

    seg = DocumentSegment(document_id=doc.id, order_index=1, content="text", char_start=0, char_end=4)
    db_session.add(seg)
    db_session.flush()

    global_doc = GlobalDocument(
        original_filename="f", file_size=100, storage_path="/tmp/f",
        content_hash="h1", mime_type="text/plain"
    )
    db_session.add(global_doc)
    db_session.flush()

    gq = GlobalQuestion(
        content_hash="qh1", stem="Q?", question_type="single_choice",
        answer="A", source_type="ai_generated",
    )
    db_session.add(gq)
    db_session.flush()

    prov = QuestionProvenance(
        question_id=gq.id,
        document_id=doc.id,
        segment_id=seg.id,
        global_document_id=global_doc.id,
        excerpt="...",
    )
    db_session.add(prov)
    db_session.flush()
    prov_id = prov.id

    ref = UserQuestionRef(
        user_id=user.id, question_id=gq.id, document_id=doc.id,
        segment_id=seg.id, collection_id=collection.id,
    )
    db_session.add(ref)
    db_session.commit()

    result = AuthManager.delete_account(db_session, user.id)

    assert result["message"] == "账号已注销"
    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(QuestionProvenance).filter(QuestionProvenance.id == prov_id).count() == 0
    assert db_session.query(UserQuestionRef).filter(UserQuestionRef.user_id == user.id).count() == 0


def test_delete_account_with_quiz_and_training(monkeypatch, db_session):
    """验证 QuizSession → QuizSessionQuestion → QuizAnswer → TrainingPlan 链路"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    user = User(
        email="quiz-test@example.com",
        password_hash="hash",
        nickname="q-test",
        is_active=True,
        dataset_id="d-2",
    )
    db_session.add(user)
    db_session.flush()

    gq = GlobalQuestion(
        content_hash="qh2", stem="Q2?", question_type="single_choice",
        answer="B", source_type="ai_generated",
    )
    db_session.add(gq)
    db_session.flush()

    session_id = "qz-sess-1"
    session = QuizSession(id=session_id, user_id=user.id, status="in_progress")
    db_session.add(session)
    db_session.flush()

    sq = QuizSessionQuestion(session_id=session_id, question_id=gq.id, order_index=1)
    db_session.add(sq)

    answer = QuizAnswer(
        session_id=session_id, question_id=gq.id, user_id=user.id,
        user_answer="B", status="correct",
    )
    db_session.add(answer)

    train = TrainingPlan(
        user_id=user.id, quiz_session_id=session_id,
        agent_session_id="agent-sess-1",
    )
    db_session.add(train)
    db_session.commit()

    result = AuthManager.delete_account(db_session, user.id)

    assert result["message"] == "账号已注销"
    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(QuizSession).filter(QuizSession.id == session_id).count() == 0
    assert db_session.query(QuizSessionQuestion).filter(QuizSessionQuestion.session_id == session_id).count() == 0
    assert db_session.query(QuizAnswer).filter(QuizAnswer.user_id == user.id).count() == 0
    assert db_session.query(TrainingPlan).filter(TrainingPlan.user_id == user.id).count() == 0


def test_delete_account_with_tutor(monkeypatch, db_session):
    """验证 TutorSession（FK → documents / document_segments）在 document 之前被删除"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    user = User(
        email="tutor-test@example.com",
        password_hash="hash",
        nickname="t-test",
        is_active=True,
        dataset_id="d-3",
    )
    db_session.add(user)
    db_session.flush()

    collection = KbCollection(user_id=user.id, name="分区", zone="study")
    db_session.add(collection)
    db_session.flush()

    doc = Document(user_id=user.id, collection_id=collection.id, display_name="doc", zone="study", content_hash="h3")
    db_session.add(doc)
    db_session.flush()

    seg = DocumentSegment(document_id=doc.id, order_index=1, content="tutor text", char_start=0, char_end=10)
    db_session.add(seg)
    db_session.flush()

    gq = GlobalQuestion(
        content_hash="qh3", stem="Tutor Q?", question_type="single_choice",
        answer="C", source_type="ai_generated",
    )
    db_session.add(gq)
    db_session.flush()

    tutor = TutorSession(
        user_id=user.id, question_id=gq.id,
        document_id=doc.id, segment_id=seg.id,
    )
    db_session.add(tutor)
    db_session.flush()
    tutor_id = tutor.id
    doc_id = doc.id
    db_session.commit()

    result = AuthManager.delete_account(db_session, user.id)

    assert result["message"] == "账号已注销"
    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(TutorSession).filter(TutorSession.id == tutor_id).count() == 0
    assert db_session.query(Document).filter(Document.id == doc_id).count() == 0


def test_delete_account_notes_tags_onboarding(monkeypatch, db_session):
    """验证 UserNote / QuestionTag / OnboardingState"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    monkeypatch.setattr(auth_service.DifyKB, "delete_dataset", lambda dataset_id: True)

    user = User(
        email="misc-test@example.com",
        password_hash="hash",
        nickname="m-test",
        is_active=True,
        dataset_id="d-4",
    )
    db_session.add(user)
    db_session.flush()

    note = UserNote(user_id=user.id, title="笔记", content_md="# 笔记")
    db_session.add(note)

    tag = QuestionTag(user_id=user.id, name="机器学习")
    db_session.add(tag)

    onboarding = OnboardingState(
        user_id=user.id, guide_version=1, revision=1,
        status="in_progress", current_step="channel",
    )
    db_session.add(onboarding)
    db_session.commit()

    result = AuthManager.delete_account(db_session, user.id)

    assert result["message"] == "账号已注销"
    assert db_session.query(User).filter(User.id == user.id).first() is None
    assert db_session.query(UserNote).filter(UserNote.user_id == user.id).count() == 0
    assert db_session.query(QuestionTag).filter(QuestionTag.user_id == user.id).count() == 0
    assert db_session.query(OnboardingState).filter(OnboardingState.user_id == user.id).count() == 0


def test_delete_account_nonexistent_user(monkeypatch, db_session):
    """用户不存在返回 404"""
    monkeypatch.setattr(AuthManager, "_invalidate_user_tokens", lambda user_id, preserve_token=None: None)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        AuthManager.delete_account(db_session, 99999)
    assert exc_info.value.status_code == 404
