"""
扫描型 PDF OCR 回退验证 — mock OCR，不依赖百度凭据或 paddle 安装
运行: cd backend && python test_pdf_ocr.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _make_blank_pdf(path: Path, pages: int = 2) -> None:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), "   \n  ", fontsize=12)
    doc.save(str(path))
    doc.close()


def test_build_shadow_markdown():
    from app.services.pdf_ocr_service import build_shadow_markdown

    md = build_shadow_markdown("教材.pdf", ["第一页内容", "第二页内容"])
    assert md.startswith("# 教材.pdf")
    assert "> OCR 提取，共 2 页" in md
    assert "## 第 1 页" in md
    assert "第一页内容" in md
    assert "## 第 2 页" in md
    print("OK build_shadow_markdown")


def test_parse_pdf_triggers_ocr_on_blank_pdf():
    from app.services.file_parser import parse_file_detailed

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "scan.pdf"
        _make_blank_pdf(pdf_path, pages=2)

        fake_md = "# scan.pdf\n\n> OCR 提取，共 2 页\n\n## 第 1 页\n\nhello\n"
        with patch(
            "app.services.pdf_ocr_service.parse_pdf_with_ocr_fallback"
        ) as mock_ocr:
            from app.services.file_parser import ParseOutcome

            mock_ocr.return_value = ParseOutcome(
                text=fake_md, error=None, ocr_used=True
            )
            outcome = parse_file_detailed(str(pdf_path), original_filename="scan.pdf")

        assert mock_ocr.called
        assert outcome.text == fake_md
        assert outcome.ocr_used is True
        print("OK parse_pdf_triggers_ocr_on_blank_pdf")


def test_parse_pdf_with_ocr_fallback_mock():
    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "scan.pdf"
        _make_blank_pdf(pdf_path, pages=1)

        with patch(
            "app.services.pdf_ocr_service._ocr_page_image",
            return_value=("识别文字", None),
        ):
            outcome = parse_pdf_with_ocr_fallback(
                str(pdf_path), original_filename="scan.pdf"
            )

        assert outcome.text is not None
        assert outcome.ocr_used is True
        assert "# scan.pdf" in outcome.text
        assert "识别文字" in outcome.text
        print("OK parse_pdf_with_ocr_fallback_mock")


def test_ocr_not_configured_error():
    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "scan.pdf"
        _make_blank_pdf(pdf_path, pages=1)

        with patch("app.core.config.OCR_BACKEND", "local"):
            with patch(
                "app.services.ocr_service.is_paddle_ocr_available", return_value=False
            ):
                with patch(
                    "app.services.ocr_service._ocr_with_paddle", return_value=None
                ):
                    outcome = parse_pdf_with_ocr_fallback(str(pdf_path))

        assert outcome.text is None
        assert outcome.error is not None
        assert "paddleocr" in outcome.error.lower()
        print("OK ocr_not_configured_error")


def test_segment_reads_ocr_markdown():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.crud import kb as kb_crud
    from app.models import User
    from app.services.segment_service import segment_document, split_text
    from app.services.storage_service import storage_service

    from app.services.pdf_ocr_service import build_shadow_markdown

    md = build_shadow_markdown("book.pdf", ["第一章内容", "第二章内容"])
    segments = split_text(md)
    assert len(segments) >= 2
    assert any(s.get("title") == "第 1 页" for s in segments)

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    with tempfile.TemporaryDirectory() as tmp:
        content = b"%PDF-1.4 fake"
        h = hashlib.sha256(content).hexdigest()
        parsed_path = storage_service.save_global_parsed(h, md)
        raw_path = str(Path(tmp) / f"{h}.pdf")
        Path(raw_path).write_bytes(content)

        user = User(
            email="ocr@test.com",
            password_hash="x",
            username="ocruser",
            nickname="OCR",
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

        count = segment_document(doc.id, db)
        db.commit()
        db.refresh(doc)

        assert doc.segment_status == "completed"
        assert count >= 2
        print("OK segment_reads_ocr_markdown")

    db.close()


def test_existing_large_pdf_one_page_if_present():
    """若 storage 中存在 665a0c… 扫描 PDF 且 PaddleOCR 可用，试跑 1 页。"""
    pdf = Path(
        r"D:\development\projects\zhishi\storage\global\66"
        r"\665a0c813ba425ca2d747df261c5c1787b304c2b974ab69e44d48d5f06a603f8.pdf"
    )
    if not pdf.exists():
        print("SKIP test_existing_large_pdf_one_page_if_present (文件不存在)")
        return

    from app.services.ocr_service import is_paddle_ocr_available
    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback

    if not is_paddle_ocr_available():
        print("SKIP test_existing_large_pdf_one_page_if_present (PaddleOCR 未安装)")
        return

    with patch("app.services.pdf_ocr_service.PDF_OCR_MAX_PAGES", 1):
        outcome = parse_pdf_with_ocr_fallback(str(pdf), original_filename="教材.pdf")

    if outcome.text:
        print(
            f"OK existing PDF OCR 1 page: {len(outcome.text)} chars, "
            f"preview={outcome.text[:120]!r}…"
        )
    else:
        print(f"WARN existing PDF OCR failed: {outcome.error}")


if __name__ == "__main__":
    test_build_shadow_markdown()
    test_parse_pdf_triggers_ocr_on_blank_pdf()
    test_parse_pdf_with_ocr_fallback_mock()
    test_ocr_not_configured_error()
    test_segment_reads_ocr_markdown()
    test_existing_large_pdf_one_page_if_present()
    print("\nAll PDF OCR checks passed.")
