"""
上传链路修复验证 — 扩展名保留 / magic bytes / Dify 文件名
运行: cd backend && python test_kb_upload_fix.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.file_parser import detect_suffix, parse_file
from app.services.storage_service import LocalStorage


def test_save_global_file_keeps_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        svc = LocalStorage(tmp)
        content = b"%PDF-1.4 fake pdf content"
        h = hashlib.sha256(content).hexdigest()
        path = svc.save_global_file(h, content, ".pdf")
        assert path.endswith(f"{h}.pdf")
        assert Path(path).exists()
        print("OK save_global_file_keeps_suffix")


def test_detect_suffix_from_magic_bytes():
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "665a0c813ba425ca2d747df261c5c1787"
        pdf_path.write_bytes(b"%PDF-1.7\n% fake large textbook")
        assert detect_suffix(str(pdf_path)) == ".pdf"
        assert detect_suffix(str(pdf_path), "notes.PDF") == ".pdf"

        docx_path = Path(tmp) / "hashonly"
        # minimal zip header only — OOXML branch may return None without word/
        docx_path.write_bytes(b"PK\x03\x04" + b"\x00" * 20)
        assert detect_suffix(str(docx_path), "report.docx") == ".docx"
        print("OK detect_suffix_from_magic_bytes")


def test_parse_file_without_path_extension():
    with tempfile.TemporaryDirectory() as tmp:
        txt_path = Path(tmp) / "nohash"
        txt_path.write_text("hello 知拾", encoding="utf-8")
        result = parse_file(str(txt_path), original_filename="readme.txt")
        assert result == "hello 知拾"
        print("OK parse_file_without_path_extension")


def test_dify_upload_uses_original_filename():
    from app.services.dify_kb import DifyKB

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "abc123.pdf"
        raw.write_bytes(b"%PDF-1.4 content")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "batch": "batch-1",
            "document": {"id": "doc-1"},
        }

        kb = DifyKB.__new__(DifyKB)
        kb.dataset_id = "ds-test"
        kb.client = MagicMock()
        kb.client.post.return_value = mock_response
        kb.headers = {}

        result = kb.add_document(str(raw), upload_filename="教材.pdf")
        assert result["document_id"] == "doc-1"
        assert "error" not in result

        call_kwargs = kb.client.post.call_args.kwargs
        uploaded_name = call_kwargs["files"]["file"][0]
        uploaded_mime = call_kwargs["files"]["file"][2]
        assert uploaded_name == "教材.pdf"
        assert uploaded_mime == "application/pdf"
        print("OK dify_upload_uses_original_filename")


def test_dify_upload_size_guard():
    from app.services.kb_service import _check_dify_upload_size

    with tempfile.TemporaryDirectory() as tmp:
        big = Path(tmp) / "big.pdf"
        big.write_bytes(b"x" * (16 * 1024 * 1024))
        # 默认不限制
        _check_dify_upload_size(str(big))
        try:
            with patch("app.services.kb_service.DIFY_MAX_UPLOAD_SIZE", 15 * 1024 * 1024):
                _check_dify_upload_size(str(big))
            assert False, "expected HTTPException"
        except Exception as exc:
            assert exc.status_code == 413
            assert "15.0 MB" in exc.detail
        print("OK dify_upload_size_guard")


def test_dify_file_too_large_returns_400():
    from fastapi import HTTPException

    from app.services.kb_service import _raise_dify_upload_error

    for http_status, error in (
        (400, "File size exceeds the limit of 15MB"),
        (413, "Request Entity Too Large"),
    ):
        try:
            _raise_dify_upload_error({"error": error, "http_status": http_status})
            assert False, f"expected HTTPException for {http_status}"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Dify Cloud" in exc.detail or "Dify 知识库" in exc.detail
    print("OK dify_file_too_large_returns_400")


if __name__ == "__main__":
    test_save_global_file_keeps_suffix()
    test_detect_suffix_from_magic_bytes()
    test_parse_file_without_path_extension()
    test_dify_upload_uses_original_filename()
    test_dify_upload_size_guard()
    test_dify_file_too_large_returns_400()
    print("\nAll upload-fix checks passed.")
