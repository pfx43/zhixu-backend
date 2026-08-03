"""扫描 PDF OCR 进度（进程内内存，供上传后轮询）"""
import threading
from typing import Optional

_lock = threading.Lock()
_by_doc: dict[str, dict] = {}
_by_hash: dict[str, dict] = {}


def set_ocr_progress(
    document_id: str,
    content_hash: str,
    status: str,
    current_page: int = 0,
    total_pages: int = 0,
    error: Optional[str] = None,
) -> None:
    entry = {
        "status": status,
        "current_page": current_page,
        "total_pages": total_pages,
        "error": error,
    }
    with _lock:
        _by_doc[document_id] = entry
        if status == "processing":
            _by_hash[content_hash] = {**entry, "document_id": document_id}
        elif status in ("completed", "failed"):
            _by_hash.pop(content_hash, None)


def get_ocr_progress(
    document_id: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> Optional[dict]:
    with _lock:
        if document_id and document_id in _by_doc:
            return dict(_by_doc[document_id])
        if content_hash and content_hash in _by_hash:
            return dict(_by_hash[content_hash])
    return None


def clear_ocr_progress(document_id: str) -> None:
    with _lock:
        _by_doc.pop(document_id, None)
