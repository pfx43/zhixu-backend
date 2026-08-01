"""
S7 聊天 citation 逻辑验证 — mock 检索命中，验证与 segment 对齐
运行: cd backend && python test_s7_citation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.crud import kb as kb_crud
from app.crud import segment as segment_crud
from app.models import User
from app.services.citation_service import (
    build_citations_from_hits,
    filter_hits_by_collection,
    resolve_chat_collection,
)
from app.services.segment_service import segment_document
from app.services.storage_service import storage_service


def _setup_study_doc(db, user, study_coll, life_coll):
    md_content = "# 第二章\n这是学习资料中的重点段落，用于 citation 测试。\n\n## 小结\n其他内容。"
    parsed_path = storage_service.save_global_parsed("hash_s7_test", md_content)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_s7_test",
        original_filename="chapter2.md",
        file_size=len(md_content.encode()),
        storage_path="/tmp/chapter2.md",
        parsed_text_path=parsed_path,
    )
    study_doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=study_coll.id,
        zone="study",
        display_name="chapter2.md",
        content_hash="hash_s7_test",
        global_document_id=global_doc.id,
        dify_document_id="dify-study-doc-001",
        parsed_cache_key=parsed_path,
    )
    life_doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=life_coll.id,
        zone="life",
        display_name="life-notes.md",
        content_hash="hash_s7_life",
        dify_document_id="dify-life-doc-001",
    )
    db.commit()
    segment_document(study_doc.id, db)
    db.commit()
    return study_doc, life_doc, md_content


def test_build_citations_aligns_with_segments():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s7@test.local",
        password_hash="x",
        username="s7user",
        nickname="S7",
        is_active=True,
        plan_level=0,
        dataset_id="ds-test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, user.dataset_id)
    db.commit()
    study_coll, life_coll = cols[0], cols[1]
    study_doc, _life_doc, md_content = _setup_study_doc(db, user, study_coll, life_coll)

    segments = segment_crud.list_segments_for_document(db, study_doc.id)
    target_seg = next(s for s in segments if s.title == "第二章")
    hit_snippet = "这是学习资料中的重点段落，用于 citation 测试。"

    mock_hits = [
        {
            "score": 0.92,
            "content": hit_snippet,
            "dify_document_id": "dify-study-doc-001",
        }
    ]

    citations = build_citations_from_hits(
        db, user.id, study_coll.id, mock_hits
    )
    assert len(citations) == 1
    c = citations[0]
    assert c.doc_id == study_doc.id
    assert c.segment_id == target_seg.id
    assert c.title == target_seg.title
    assert c.char_start == target_seg.char_start
    assert c.char_end == target_seg.char_end
    assert hit_snippet in (c.snippet or "")
    assert md_content[c.char_start : c.char_end] == target_seg.content

    print("OK build_citations_aligns_with_segments")
    db.close()


def test_filter_hits_by_collection():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s7f@test.local",
        password_hash="x",
        username="s7fuser",
        nickname="S7F",
        is_active=True,
        plan_level=0,
        dataset_id="ds-test",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, user.dataset_id)
    db.commit()
    study_coll, life_coll = cols[0], cols[1]
    _study_doc, life_doc, _md = _setup_study_doc(db, user, study_coll, life_coll)

    hits = [
        {"score": 0.9, "content": "生活区笔记", "dify_document_id": "dify-life-doc-001"},
        {"score": 0.8, "content": "学习区内容", "dify_document_id": "dify-study-doc-001"},
    ]

    life_hits = filter_hits_by_collection(db, user.id, life_coll.id, hits)
    assert len(life_hits) == 1
    assert life_hits[0]["dify_document_id"] == "dify-life-doc-001"

    life_citations = build_citations_from_hits(
        db, user.id, life_coll.id, life_hits
    )
    assert len(life_citations) == 1
    assert life_citations[0].doc_id == life_doc.id
    assert life_citations[0].segment_id is None
    assert life_citations[0].char_start is None
    assert life_citations[0].char_end is None

    print("OK filter_hits_by_collection")
    db.close()


def test_resolve_chat_collection_defaults_to_study():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s7r@test.local",
        password_hash="x",
        username="s7ruser",
        nickname="S7R",
        is_active=True,
        plan_level=0,
        dataset_id="ds-user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    coll, dataset_id = resolve_chat_collection(db, user.id, None, user.dataset_id)
    assert coll.zone == "study"
    assert coll.is_default is True
    assert dataset_id == "ds-user"

    print("OK resolve_chat_collection_defaults_to_study")
    db.close()


if __name__ == "__main__":
    test_build_citations_aligns_with_segments()
    test_filter_hits_by_collection()
    test_resolve_chat_collection_defaults_to_study()
    print("\nAll S7 citation tests passed.")
