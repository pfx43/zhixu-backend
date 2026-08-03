"""
文档页解析 — 从 parsed.txt 按 `## 第 N 页` 切分，供出题页展示
"""
import re
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud import kb as kb_crud
from app.crud import segment as segment_crud
from app.models import Document
from app.schemas.page import (
    DocumentPageDetailOut,
    DocumentPageListOut,
    DocumentPageOut,
)
from app.services.knowledge.file_parser import get_pdf_page_count
from app.services.knowledge.segment_service import _load_document_text, _resolve_parsed_path
from app.services.knowledge.storage_service import storage_service

PAGE_HEADING_PATTERN = re.compile(r"^##\s+第\s+(\d+)\s+页\s*$", re.MULTILINE)
BUILTIN_Q_PATTERNS = (
    re.compile(r"[A-D][\.、．]\s"),
    re.compile(r"[（\(][A-D][）\)]"),
    re.compile(r"(单选|多选|判断|习题|练习|思考题|测验|例题)"),
)
KEY_PAGE_PATTERN = re.compile(r"(重点|小结|本章|总结|考点|关键|核心)")


def _analyze_page_content(content: str) -> tuple[bool, bool]:
    text = content.strip()
    has_builtin = any(p.search(text) for p in BUILTIN_Q_PATTERNS)
    is_key = len(text) > 300 or bool(KEY_PAGE_PATTERN.search(text))
    return has_builtin, is_key


def _resolve_storage_path(document: Document) -> Optional[str]:
    global_doc = document.global_document
    if global_doc and global_doc.storage_path:
        path = Path(global_doc.storage_path)
        if path.is_file():
            return str(path)
    return None


def _is_pdf_document(document: Document) -> bool:
    global_doc = document.global_document
    if global_doc:
        if global_doc.mime_type == "application/pdf":
            return True
        if global_doc.original_filename.lower().endswith(".pdf"):
            return True
        if global_doc.storage_path.lower().endswith(".pdf"):
            return True
    return document.display_name.lower().endswith(".pdf")


def _preview_mode_for_document(document: Document) -> str:
    return "pdf" if _is_pdf_document(document) else "markdown"


def _empty_pdf_pages(total: int) -> List[dict]:
    pages: List[dict] = []
    for page_num in range(1, total + 1):
        pages.append(
            {
                "page_number": page_num,
                "title": f"第 {page_num} 页",
                "content": "",
                "char_start": 0,
                "char_end": 0,
                "has_builtin_questions": False,
                "is_key_page": False,
                "preview_mode": "pdf",
            }
        )
    return pages


def _expand_single_page_pdf(document: Document, pages_raw: List[dict]) -> List[dict]:
    """单页「全文」且原文件为 PDF 时，按 PDF 实际页数展开列表。"""
    if len(pages_raw) != 1 or pages_raw[0].get("title") != "全文":
        return pages_raw
    if not _is_pdf_document(document):
        return pages_raw
    storage_path = _resolve_storage_path(document)
    if not storage_path:
        return pages_raw
    total = get_pdf_page_count(storage_path)
    if total <= 1:
        return pages_raw

    full_content = pages_raw[0]["content"]
    chunks = [c.strip() for c in re.split(r"\n{2,}", full_content) if c.strip()]
    expanded = _empty_pdf_pages(total)
    for i, page in enumerate(expanded):
        if i < len(chunks):
            body = chunks[i]
            has_builtin, is_key = _analyze_page_content(body)
            page["content"] = body
            page["has_builtin_questions"] = has_builtin
            page["is_key_page"] = is_key
    return expanded


def _page_out(document: Document, page: dict) -> DocumentPageOut:
    preview_mode = page.get("preview_mode") or _preview_mode_for_document(document)
    return DocumentPageOut(
        page_number=page["page_number"],
        title=page["title"],
        preview=_make_preview(page["content"]),
        char_start=page["char_start"],
        char_end=page["char_end"],
        content_length=len(page["content"]),
        has_builtin_questions=page["has_builtin_questions"],
        is_key_page=page["is_key_page"],
        segment_id=page.get("segment_id"),
        preview_mode=preview_mode,
        file_type="pdf" if preview_mode == "pdf" else None,
    )


def _make_preview(content: str, max_len: int = 120) -> str:
    text = re.sub(r"\s+", " ", content.strip())
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def split_pages(text: str) -> List[dict]:
    """
    按 `## 第 N 页` 切分全文。
    无页标记时返回单页（page_number=1，内容为全文）。
    """
    if not text or not text.strip():
        return []

    matches = list(PAGE_HEADING_PATTERN.finditer(text))
    if not matches:
        has_builtin, is_key = _analyze_page_content(text)
        return [
            {
                "page_number": 1,
                "title": "全文",
                "content": text,
                "char_start": 0,
                "char_end": len(text),
                "has_builtin_questions": has_builtin,
                "is_key_page": is_key,
            }
        ]

    pages: List[dict] = []
    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        content_start = match.end()
        content_end = (
            matches[i + 1].start() if i + 1 < len(matches) else len(text)
        )
        chunk = text[content_start:content_end].strip()
        has_builtin, is_key = _analyze_page_content(chunk)
        pages.append(
            {
                "page_number": page_num,
                "title": f"第 {page_num} 页",
                "content": chunk,
                "char_start": match.start(),
                "char_end": content_end,
                "has_builtin_questions": has_builtin,
                "is_key_page": is_key,
            }
        )
    return pages


def _find_segment_id_for_page(
    db: Session, document_id: str, page: dict
) -> Optional[str]:
    """OCR 文档分段标题常为「第 N 页」，尝试匹配 segment。"""
    title = page["title"]
    segments = segment_crud.list_segments_for_document(db, document_id)
    for seg in segments:
        if seg.title and seg.title.strip() == title.strip():
            return seg.id
        if (
            seg.char_start <= page["char_start"] < seg.char_end
            or seg.char_start < page["char_end"] <= seg.char_end
        ):
            return seg.id
    return None


def _strip_page_heading(content: str) -> str:
    """去掉页文件首行 `## 第 N 页`，返回正文。"""
    lines = content.splitlines()
    if lines and PAGE_HEADING_PATTERN.match(lines[0].strip()):
        return "\n".join(lines[1:]).strip()
    return content.strip()


def _pages_from_folder(
    db: Session, document: Document, parsed_path: str
) -> tuple[List[dict], bool]:
    """从按页文件夹加载，无需 split 全文。"""
    manifest = storage_service.read_parsed_manifest(parsed_path)
    header_len = 0
    if manifest:
        name = manifest.get("original_filename") or document.display_name or "document"
        total = manifest.get("total_pages") or 0
        header = f"# {name}\n\n> OCR 提取，共 {total} 页\n\n"
        header_len = len(header)

    raw_pages = storage_service.list_parsed_pages(parsed_path, include_content=True)
    pages: List[dict] = []
    char_offset = header_len
    for item in raw_pages:
        full_content = item["content"]
        body = _strip_page_heading(full_content)
        has_builtin, is_key = _analyze_page_content(body)
        content_start = char_offset
        content_end = char_offset + len(full_content)
        char_offset = content_end + 2
        page = {
            "page_number": item["page_number"],
            "title": item["title"],
            "content": body,
            "char_start": content_start,
            "char_end": content_end,
            "has_builtin_questions": has_builtin,
            "is_key_page": is_key,
        }
        page["segment_id"] = _find_segment_id_for_page(db, document.id, page)
        pages.append(page)
    return pages, True


def _load_pages_for_document(
    db: Session, document: Document
) -> tuple[List[dict], bool]:
    parsed_path = _resolve_parsed_path(document)
    if parsed_path and storage_service.is_parsed_pages_dir(parsed_path):
        pages, has_markers = _pages_from_folder(db, document, parsed_path)
        if _is_pdf_document(document):
            for page in pages:
                page.setdefault("preview_mode", "pdf")
        return pages, has_markers

    text, error = _load_document_text(document)
    if text is None:
        storage_path = _resolve_storage_path(document)
        if storage_path and _is_pdf_document(document):
            total = get_pdf_page_count(storage_path)
            if total > 0:
                pages = _empty_pdf_pages(total)
                for page in pages:
                    page["segment_id"] = _find_segment_id_for_page(
                        db, document.id, page
                    )
                return pages, True
        raise HTTPException(status_code=400, detail=error or "无法读取文档内容")

    has_markers = PAGE_HEADING_PATTERN.search(text) is not None
    pages = split_pages(text)
    pages = _expand_single_page_pdf(document, pages)
    for page in pages:
        page["segment_id"] = _find_segment_id_for_page(db, document.id, page)
        if _is_pdf_document(document):
            page.setdefault("preview_mode", "pdf")
    return pages, has_markers


def list_document_pages(
    db: Session, user_id: int, doc_id: str
) -> DocumentPageListOut:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    pages_raw, has_markers = _load_pages_for_document(db, doc)
    pages = [_page_out(doc, p) for p in pages_raw]
    preview_mode = _preview_mode_for_document(doc)
    return DocumentPageListOut(
        document_id=doc.id,
        document_name=doc.display_name,
        total_pages=len(pages),
        has_page_markers=has_markers,
        preview_mode=preview_mode,
        file_type="pdf" if preview_mode == "pdf" else None,
        has_raw_file=_resolve_storage_path(doc) is not None,
        pages=pages,
    )


def get_document_page_detail(
    db: Session, user_id: int, doc_id: str, page_number: int
) -> DocumentPageDetailOut:
    doc = kb_crud.get_document_by_id_or_dify(db, user_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    parsed_path = _resolve_parsed_path(doc)
    if parsed_path and storage_service.is_parsed_pages_dir(parsed_path):
        raw = storage_service.read_page_at_path(parsed_path, page_number)
        if raw is None:
            raise HTTPException(status_code=404, detail=f"页码不存在: {page_number}")
        body = _strip_page_heading(raw)
        has_builtin, is_key = _analyze_page_content(body)
        page = {
            "page_number": page_number,
            "title": f"第 {page_number} 页",
            "content": body,
            "char_start": 0,
            "char_end": len(raw),
            "has_builtin_questions": has_builtin,
            "is_key_page": is_key,
        }
        if _is_pdf_document(doc):
            page["preview_mode"] = "pdf"
        page["segment_id"] = _find_segment_id_for_page(db, doc.id, page)
        target = page
    else:
        pages_raw, _ = _load_pages_for_document(db, doc)
        target = next((p for p in pages_raw if p["page_number"] == page_number), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"页码不存在: {page_number}")

    base = _page_out(doc, target)
    return DocumentPageDetailOut(
        **base.model_dump(),
        content=target["content"],
    )


def get_pages_by_numbers(
    db: Session, document: Document, page_numbers: List[int]
) -> List[dict]:
    pages_raw, _ = _load_pages_for_document(db, document)
    by_num = {p["page_number"]: p for p in pages_raw}
    result = []
    for num in page_numbers:
        if num not in by_num:
            raise HTTPException(status_code=404, detail=f"页码不存在: {num}")
        result.append(by_num[num])
    return result
