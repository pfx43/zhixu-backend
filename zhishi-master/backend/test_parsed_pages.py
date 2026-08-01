"""
OCR 按页文件夹格式验证
运行: cd backend && python test_parsed_pages.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_save_and_read_pages_folder():
    from app.services.storage_service import storage_service

    h = hashlib.sha256(b"pages-test").hexdigest()
    page_texts = ["第一页正文", "第二页正文"]
    folder = storage_service.save_global_parsed_pages(
        h, page_texts, original_filename="test.pdf", ocr_used=True
    )

    assert storage_service.is_parsed_pages_dir(folder)
    assert not Path(folder).name.endswith(".parsed.txt")

    pages_dir = Path(folder) / "pages"
    assert (pages_dir / "page_001.md").is_file()
    assert (pages_dir / "page_002.md").is_file()
    assert (Path(folder) / "manifest.json").is_file()

    combined = storage_service.read_text_at_path(folder)
    assert combined is not None
    assert "## 第 1 页" in combined
    assert "第一页正文" in combined
    assert "## 第 2 页" in combined

    page2 = storage_service.read_page_at_path(folder, 2)
    assert page2 is not None
    assert "第二页正文" in page2

    listed = storage_service.list_parsed_pages(folder)
    assert len(listed) == 2
    assert listed[0]["page_number"] == 1

    storage_service.delete_file_at_path(folder)
    assert not Path(folder).exists()
    print("OK save_and_read_pages_folder")


def test_page_service_folder_fast_path():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.crud import kb as kb_crud
    from app.models import User
    from app.services.page_service import (
        get_document_page_detail,
        list_document_pages,
        split_pages,
    )
    from app.services.segment_service import segment_document
    from app.services.storage_service import storage_service

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    with tempfile.TemporaryDirectory() as tmp:
        content = b"%PDF-1.4 fake"
        h = hashlib.sha256(content).hexdigest()
        page_texts = [f"第{i}页内容" for i in range(1, 6)]
        parsed_path = storage_service.save_global_parsed_pages(
            h, page_texts, original_filename="book.pdf"
        )
        raw_path = str(Path(tmp) / f"{h}.pdf")
        Path(raw_path).write_bytes(content)

        user = User(
            email="pages@test.com",
            password_hash="x",
            username="pagesuser",
            nickname="Pages",
            is_active=True,
            plan_level=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        kb_crud.seed_default_collections(db, user.id, None)
        coll = kb_crud.get_default_study_collection(db, user.id)
        gdoc = kb_crud.create_global_document(
            db,
            content_hash=h,
            original_filename="book.pdf",
            file_size=len(content),
            storage_path=raw_path,
            mime_type="application/pdf",
            parsed_text_path=parsed_path,
        )
        doc = kb_crud.create_document(
            db,
            user_id=user.id,
            collection_id=coll.id,
            zone="study",
            display_name="book.pdf",
            content_hash=h,
            global_document_id=gdoc.id,
            parsed_cache_key=parsed_path,
        )
        db.commit()

        listing = list_document_pages(db, user.id, doc.id)
        assert listing.total_pages == 5
        assert listing.has_page_markers is True
        assert len(listing.pages) == 5
        assert listing.pages[0].preview.startswith("第1页")

        detail = get_document_page_detail(db, user.id, doc.id, 3)
        assert detail.page_number == 3
        assert "第3页内容" in detail.content

        count = segment_document(doc.id, db)
        db.commit()
        db.refresh(doc)
        assert doc.segment_status == "completed"
        assert count >= 5

        storage_service.delete_file_at_path(parsed_path)
        print("OK page_service_folder_fast_path")

    db.close()


def test_legacy_parsed_txt_fallback():
    from app.services.page_service import split_pages
    from app.services.storage_service import storage_service

    h = hashlib.sha256(b"legacy").hexdigest()
    md = "# doc\n\n## 第 1 页\n\nA\n\n## 第 2 页\n\nB\n"
    legacy_path = storage_service.save_global_parsed(h, md)

    assert not storage_service.is_parsed_pages_dir(legacy_path)
    text = storage_service.read_text_at_path(legacy_path)
    pages = split_pages(text or "")
    assert len(pages) == 2
    assert pages[0]["content"].strip() == "A"

    storage_service.delete_file_at_path(legacy_path)
    print("OK legacy_parsed_txt_fallback")


if __name__ == "__main__":
    test_save_and_read_pages_folder()
    test_legacy_parsed_txt_fallback()
    test_page_service_folder_fast_path()
    print("\nAll parsed pages checks passed.")
