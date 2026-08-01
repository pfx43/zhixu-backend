"""
S3 文档分段逻辑验证 — 不启动 HTTP 服务、不依赖 Dify
运行: cd backend && python test_s3_segment.py
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
from app.services.segment_service import segment_document, split_text
from app.services.storage_service import storage_service


def test_split_by_headings():
    text = "# 第一章\n内容一\n\n## 1.1 小节\n内容二\n\n# 第二章\n内容三"
    segments = split_text(text)
    assert len(segments) == 3
    assert segments[0]["title"] == "第一章"
    assert segments[1]["title"] == "1.1 小节"
    assert segments[2]["title"] == "第二章"
    for seg in segments:
        assert text[seg["char_start"] : seg["char_end"]] == seg["content"]
    print("OK split_by_headings")


def test_split_by_window():
    text = "a" * 3200
    segments = split_text(text)
    assert len(segments) >= 2
    assert segments[0]["char_start"] == 0
    assert segments[0]["char_end"] == 1500
    assert segments[1]["char_start"] == 1300
    for seg in segments:
        assert text[seg["char_start"] : seg["char_end"]] == seg["content"]
    print("OK split_by_window")


def test_segment_document_study():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s3@test.local",
        password_hash="x",
        username="s3user",
        nickname="S3",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()
    study_coll = cols[0]

    md_content = "# 导论\n这是学习资料。\n\n## 要点\n重点内容。"
    parsed_path = storage_service.save_global_parsed("hash_s3_test", md_content)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="hash_s3_test",
        original_filename="notes.md",
        file_size=len(md_content.encode()),
        storage_path="/tmp/notes.md",
        parsed_text_path=parsed_path,
    )
    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=study_coll.id,
        zone="study",
        display_name="notes.md",
        content_hash="hash_s3_test",
        global_document_id=global_doc.id,
        parsed_cache_key=parsed_path,
    )
    db.commit()

    count = segment_document(doc.id, db)
    db.commit()
    db.refresh(doc)

    assert count == 2
    assert doc.segment_status == "completed"
    rows = segment_crud.list_segments_for_document(db, doc.id)
    assert len(rows) == 2
    assert rows[0].title == "导论"
    assert rows[1].title == "要点"
    for row in rows:
        assert md_content[row.char_start : row.char_end] == row.content

    print("OK segment_document_study")
    db.close()


def test_segment_skips_life_zone():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s3life@test.local",
        password_hash="x",
        username="s3life",
        nickname="S3Life",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()
    life_coll = cols[1]

    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=life_coll.id,
        zone="life",
        display_name="life.md",
        content_hash="life_hash",
    )
    db.commit()

    count = segment_document(doc.id, db)
    db.commit()
    db.refresh(doc)

    assert count == 0
    assert doc.segment_status == "not_started"
    assert segment_crud.list_segments_for_document(db, doc.id) == []
    print("OK segment_skips_life_zone")
    db.close()


def test_resegment_deletes_old():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(
        email="s3re@test.local",
        password_hash="x",
        username="s3re",
        nickname="S3Re",
        is_active=True,
        plan_level=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    cols = kb_crud.seed_default_collections(db, user.id, None)
    db.commit()

    text_v1 = "# 旧版\n内容"
    path_v1 = storage_service.save_global_parsed("reseg_hash", text_v1)
    global_doc = kb_crud.create_global_document(
        db,
        content_hash="reseg_hash",
        original_filename="a.md",
        file_size=10,
        storage_path="/tmp/a.md",
        parsed_text_path=path_v1,
    )
    doc = kb_crud.create_document(
        db,
        user_id=user.id,
        collection_id=cols[0].id,
        zone="study",
        display_name="a.md",
        content_hash="reseg_hash",
        global_document_id=global_doc.id,
        parsed_cache_key=path_v1,
    )
    db.commit()

    segment_document(doc.id, db)
    db.commit()
    assert len(segment_crud.list_segments_for_document(db, doc.id)) == 1

    text_v2 = "# 新版\n新内容\n\n## 小节\n更多"
    path_v2 = storage_service.save_global_parsed("reseg_hash_v2", text_v2)
    doc.parsed_cache_key = path_v2
    db.commit()

    segment_document(doc.id, db)
    db.commit()
    rows = segment_crud.list_segments_for_document(db, doc.id)
    assert len(rows) == 2
    assert rows[0].title == "新版"

    print("OK resegment_deletes_old")
    db.close()


if __name__ == "__main__":
    test_split_by_headings()
    test_split_by_window()
    test_segment_document_study()
    test_segment_skips_life_zone()
    test_resegment_deletes_old()
    print("\nAll S3 checks passed.")
