"""
S4 出题逻辑验证 — mock LLM，不依赖 Tina / HTTP
运行: cd backend && python test_s4_questions.py
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
from app.crud import segment as segment_crud
from app.models import GlobalQuestion, User, UserQuestionRef
from app.services.question_gen_service import generate_questions
from app.services.question_hash import compute_content_hash, normalize_text
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
            "explanation": "测试解析",
            "tags": ["测试"],
        }
    ]


def _mock_provider_duplicate(segment):
    """两段返回相同题干，用于验证 global_questions 去重。"""
    return [
        {
            "stem": "这是一道去重测试题？",
            "options": [
                {"key": "A", "text": "是"},
                {"key": "B", "text": "否"},
            ],
            "answer": "A",
            "explanation": "去重",
            "tags": [],
        }
    ]


def _setup_study_doc(db):
    user = User(
        email="s4@test.local",
        password_hash="x",
        username="s4user",
        nickname="S4",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()

    md = "# 导论\n学习资料内容。\n\n## 要点\n重点内容。"
    parsed_path = storage_service.save_global_parsed("hash_s4_test", md)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_s4_test",
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
        content_hash="hash_s4_test",
        global_document_id=global_doc.id,
        parsed_cache_key=parsed_path,
    )
    db.commit()
    segment_document(doc.id, db)
    db.commit()
    db.refresh(doc)
    return user, doc


def test_content_hash_normalize():
    h1 = compute_content_hash(
        "  题干？  ",
        [{"key": "A", "text": "选项 A"}],
        "A",
    )
    h2 = compute_content_hash(
        "题干",
        [{"key": "A", "text": "选项A"}],
        "a",
    )
    assert h1 == h2
    assert normalize_text("  Hello, World!  ") == "helloworld"
    print("OK content_hash_normalize")


def test_generate_questions_study():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_study_doc(db)
    result = generate_questions(
        db, user.id, document_id=doc.id, provider=_mock_provider
    )
    db.commit()
    db.refresh(doc)

    assert result.question_gen_status == "completed"
    assert result.total_questions >= 1
    assert doc.question_gen_status == "completed"

    refs = db.query(UserQuestionRef).filter(UserQuestionRef.user_id == user.id).all()
    assert len(refs) >= 1

    gq = db.query(GlobalQuestion).all()
    assert len(gq) >= 1

    prov = question_crud.list_provenance_for_question(db, gq[0].id)
    assert len(prov) >= 1
    assert prov[0].segment_id is not None
    assert prov[0].excerpt

    detail = question_crud.list_user_questions(db, user.id, document_id=doc.id)
    assert len(detail) >= 1

    print("OK generate_questions_study")
    db.close()


def test_deduplication():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_study_doc(db)
    segments = segment_crud.list_segments_for_document(db, doc.id)
    assert len(segments) >= 2

    result = generate_questions(
        db, user.id, document_id=doc.id, provider=_mock_provider_duplicate
    )
    db.commit()

    assert result.total_questions == 2
    assert result.questions_created == 1
    assert result.questions_reused == 1

    global_count = db.query(GlobalQuestion).count()
    assert global_count == 1

    prov_count = len(question_crud.list_provenance_for_question(db, db.query(GlobalQuestion).first().id))
    assert prov_count == 2

    print("OK deduplication")
    db.close()


def test_skips_life_zone():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s4life@test.local",
        password_hash="x",
        username="s4life",
        nickname="S4Life",
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
        collection_id=cols[1].id,
        zone="life",
        display_name="life.md",
        content_hash="life_s4",
    )
    db.commit()

    try:
        generate_questions(db, user.id, document_id=doc.id, provider=_mock_provider)
        assert False, "should raise"
    except HTTPException as e:
        assert "学习区" in str(e.detail)

    print("OK skips_life_zone")
    db.close()


def test_skips_incomplete_segment():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s4inc@test.local",
        password_hash="x",
        username="s4inc",
        nickname="S4Inc",
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
        display_name="pending.md",
        content_hash="pending_s4",
    )
    doc.segment_status = "not_started"
    db.commit()

    try:
        generate_questions(db, user.id, document_id=doc.id, provider=_mock_provider)
        assert False, "should raise"
    except HTTPException as e:
        assert "分段" in str(e.detail)

    print("OK skips_incomplete_segment")
    db.close()


def test_get_question_detail_provenance():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user, doc = _setup_study_doc(db)
    generate_questions(db, user.id, document_id=doc.id, provider=_mock_provider)
    db.commit()

    from app.services.question_gen_service import get_question_detail

    ref = db.query(UserQuestionRef).filter(UserQuestionRef.user_id == user.id).first()
    detail = get_question_detail(db, user.id, ref.question_id)

    assert detail.stem
    assert len(detail.provenance) >= 1
    assert detail.provenance[0].segment_id
    assert detail.provenance[0].excerpt

    print("OK get_question_detail_provenance")
    db.close()


if __name__ == "__main__":
    test_content_hash_normalize()
    test_generate_questions_study()
    test_deduplication()
    test_skips_life_zone()
    test_skips_incomplete_segment()
    test_get_question_detail_provenance()
    print("\nAll S4 checks passed.")
